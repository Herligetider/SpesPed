"""Explicit recipient review, immutable packages, authorization and durable release.

Mutations own transactions. No schedule or approval calls dispatch. Release writes
an unknown outcome *before* crossing the wire: a lost process/reply can only be
reconciled with that exact persisted key, never submitted again blindly.
"""
import base64,hashlib
from datetime import datetime,timedelta
from functools import wraps
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError
from spesped.auth import Actor,require_school_access,require_learner_access,require_authority,school_today
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError,access_denied
from spesped.contexts.identity.models import School,GuardianRelationship,UserAccount,LoginSession
from spesped.contexts.documents import service as documents
from spesped.contexts.documents.adapters import encode,digest
from spesped.contexts.curriculum.service import sources
from . import models as m,schemas as s
from .adapters import owner_reader,read_contract
from .transports import TransportRegistry,TransportOutcome,PROTOCOL

def conflict(message='Reload the exact current communication revision before retrying.'):
    return DomainError('communication_conflict',message,409)
def get(db,model,school_id,identity,expected=None,lock=False):
    query=select(model).where(model.school_id==school_id,model.id==str(identity)).execution_options(populate_existing=True)
    if lock:query=query.with_for_update()
    row=db.scalar(query)
    if row is None:raise access_denied()
    if expected is not None and row.version!=expected:raise conflict()
    return row
def current(db,row,model,field):return db.scalar(select(model).where(model.school_id==row.school_id,getattr(model,field)==row.id,model.number==row.current_revision))
def row_json(row):return encode({v.name:getattr(row,v.name) for v in row.__table__.columns})
def access(db,actor,school_id,learner_id,action):return require_learner_access(db,actor,school_id,learner_id,action)
def school_access(db,actor,school_id,action):
    member=require_school_access(db,actor,school_id)
    if member.role in {'guardian','technical_administrator'}:raise access_denied()
    return require_authority(db,actor,school_id,action)
def authority(db,actor,school_id,action,learner_id=None):
    grant=require_authority(db,actor,school_id,action,learner_id=learner_id)
    db.refresh(grant)
    return encode({'id':grant.id,'version':grant.version,'action':grant.action,'person_id':actor.user_id,'learner_id':grant.learner_id,'valid_from':grant.valid_from,'valid_until':grant.valid_until})
def authority_current(db,school_id,person_id,binding,learner_id=None):
    with owner_reader(db) as reader:
        try:return authority(reader,Actor(person_id),school_id,binding['action'],learner_id)==binding
        except DomainError:return False

def event(db,actor,row,action,**payload):
    db.flush();now=utcnow();record_audit(db,actor,row.school_id,action,row.__tablename__,row.id)
    db.add(m.CommunicationEvent(school_id=row.school_id,aggregate_id=row.id,aggregate_version=row.version,actor_id=actor.user_id,event_type=action,payload=encode(payload),causation_id=db.info['communication_request_key'],correlation_id=db.info['communication_correlation_id'],occurred_at=now,recorded_at=now,schema_version=1));db.flush()
def action_access(db,actor,school_id,kind,action,identity,command):
    if kind=='channel':school_access(db,actor,school_id,action);return
    if kind=='recipient':
        learner=str(command.learner_id) if hasattr(command,'learner_id') else get(db,m.RecipientClearance,school_id,identity).learner_id
    elif kind=='package':
        learner=str(command.selection.learner_id) if hasattr(command,'selection') else get(db,m.DisclosurePackage,school_id,identity).learner_id
        if identity:
            if get(db,m.DisclosurePackage,school_id,identity).learner_id!=learner:raise access_denied()
    elif kind=='dispatch':
        dispatch=get(db,m.Dispatch,school_id,identity);learner=get(db,m.DisclosurePackage,school_id,dispatch.package_id).learner_id
    elif kind=='portal':
        portal=get(db,m.PortalAccessGrant,school_id,identity)
        if action.startswith('portal.'):
            portal_access(db,actor,school_id,portal,db.info.get('communication_session_id'),require_bound=action!='portal.open');return
        learner=get(db,m.DisclosurePackage,school_id,get(db,m.Dispatch,school_id,portal.dispatch_id).package_id).learner_id
    access(db,actor,school_id,learner,action)
    if action in {'communication.content.review','communication.authorize','communication.recipient.review'}:authority(db,actor,school_id,action,learner)
def mutation(action,kind):
    def decorate(fn):
        @wraps(fn)
        def mutate(db,actor,school_id,*args):
            # Refuse caller-owned work before entering our rollback/metadata scope.
            # This precondition must not discard a staged protective restriction.
            if any(type(v).__module__.startswith('spesped.contexts.') for v in db.new|db.dirty|db.deleted):raise DomainError('dependency_pending','Commit staged changes separately before communication commands.',409)
            previous={k:db.info.get(k) for k in ('communication_request_key','communication_correlation_id')}
            try:
                require_school_access(db,actor,school_id);db.scalar(select(School.id).where(School.id==school_id).with_for_update())
                command=args[-1];identity=args[0] if len(args)>1 else None
                action_access(db,actor,school_id,kind,action,identity,command)
                db.info['communication_request_key']=command.request_key;db.info['communication_correlation_id']=str(uuid4())
                fingerprint=digest({'operation':fn.__name__,'target':[str(v) for v in args[:-1]],'command':command.model_dump(mode='json')})
                prior=db.scalar(select(m.CommunicationCommand).where(m.CommunicationCommand.school_id==school_id,m.CommunicationCommand.actor_id==actor.user_id,m.CommunicationCommand.request_key==command.request_key))
                db.info['communication_command_replayed']=prior is not None
                if prior:
                    if prior.digest!=fingerprint:raise DomainError('idempotency_conflict','The request key belongs to a different communication command.',409)
                    # Replays retain original-action authorization, including exact human authorities.
                    value=view(db,actor,school_id,prior.target_kind,prior.target_id);db.commit();return value
                row=fn(db,actor,school_id,*args)
                db.add(m.CommunicationCommand(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,operation=fn.__name__,digest=fingerprint,target_kind=kind,target_id=row.id));db.flush()
                value=view(db,actor,school_id,kind,row.id);db.commit();return value
            except (StaleDataError,DBAPIError) as exc:
                db.rollback()
                if isinstance(exc,StaleDataError) or getattr(getattr(exc,'orig',None),'sqlstate',None) in {'40001','40P01','55P03','23505'} or 'UNIQUE constraint failed' in str(getattr(exc,'orig','')):raise conflict('A concurrent command won. Retry the same request key.') from None
                raise
            except Exception:db.rollback();raise
            finally:
                for k,v in previous.items():
                    if v is None:db.info.pop(k,None)
                    else:db.info[k]=v
        return mutate
    return decorate

def exact(row,revision,command):
    if revision.id!=str(command.revision_id) or revision.digest!=command.content_digest:raise conflict()
def checked_sources(db,actor,school_id,refs,learner_id=None):
    for ref in refs:
        value=ref.model_dump(mode='json') if hasattr(ref,'model_dump') else ref
        if value.get('case_id') or (value.get('learner_id') and value['learner_id']!=learner_id):raise access_denied()
    with owner_reader(db) as reader:return encode(sources(reader,actor,school_id,refs,'read'))
def settings_current(settings):
    if datetime.fromisoformat(settings['expires_at'].replace('Z','+00:00'))<=utcnow():raise conflict('The reviewed policy or recipient clearance expired.')
def channel_ready(db,actor,school_id,revision_id,purpose=None,kind=None):
    revision=get(db,m.ChannelRevision,school_id,revision_id);row=get(db,m.ChannelPolicy,school_id,revision.policy_id)
    if row.state!='active' or row.current_revision!=revision.number or digest(revision.settings)!=revision.digest:raise conflict('Select the exact current reviewed channel policy.')
    settings_current(revision.settings);review=db.scalar(select(m.ChannelReview).where(m.ChannelReview.school_id==school_id,m.ChannelReview.revision_id==revision.id))
    if review is None or review.digest!=revision.digest or not authority_current(db,school_id,review.reviewer_id,review.authority):raise conflict('The channel policy requires current human review.')
    checked_sources(db,Actor(review.reviewer_id),school_id,revision.settings['sources'])
    if purpose and purpose not in revision.settings['purposes']:raise conflict('This purpose is outside the reviewed channel policy.')
    if kind and kind not in revision.settings['document_kinds']:raise conflict('This document kind is outside the reviewed channel policy.')
    return revision
@mutation('communication.policy.manage','channel')
def create_channel(db,actor,school_id,command):
    checked_sources(db,actor,school_id,command.settings.sources);settings=command.settings.model_dump(mode='json');settings_current(settings)
    row=m.ChannelPolicy(school_id=school_id,state='active');db.add(row);db.flush();db.add(m.ChannelRevision(school_id=school_id,policy_id=row.id,number=1,settings=settings,digest=digest(settings),author_id=actor.user_id));event(db,actor,row,'communication.channel.created');return row
@mutation('communication.policy.manage','channel')
def change_channel(db,actor,school_id,identity,command):
    row=get(db,m.ChannelPolicy,school_id,identity,command.expected_version);checked_sources(db,actor,school_id,command.settings.sources);settings=command.settings.model_dump(mode='json');settings_current(settings)
    row.current_revision+=1;row.version+=1;row.state='active';db.add(m.ChannelRevision(school_id=school_id,policy_id=row.id,number=row.current_revision,settings=settings,digest=digest(settings),author_id=actor.user_id));event(db,actor,row,'communication.channel.changed');return row
@mutation('communication.policy.review','channel')
def review_channel(db,actor,school_id,identity,command):
    row=get(db,m.ChannelPolicy,school_id,identity,command.expected_version);revision=current(db,row,m.ChannelRevision,'policy_id');exact(row,revision,command);settings_current(revision.settings);checked_sources(db,actor,school_id,revision.settings['sources'])
    binding=authority(db,actor,school_id,'communication.policy.review');db.add(m.ChannelReview(school_id=school_id,revision_id=revision.id,digest=revision.digest,reviewer_id=actor.user_id,authority=binding,reason=command.reason));row.version+=1;event(db,actor,row,'communication.channel.reviewed');return row
@mutation('communication.policy.review','channel')
def revoke_channel(db,actor,school_id,identity,command):
    row=get(db,m.ChannelPolicy,school_id,identity,command.expected_version);row.state='revoked';row.version+=1;event(db,actor,row,'communication.channel.revoked');return row

def relationship_binding(db,school_id,learner_id,identity,lock=False):
    relationship=get(db,GuardianRelationship,school_id,identity,lock=lock);school=db.get(School,school_id,populate_existing=True);today=school_today(school)
    user=db.get(UserAccount,relationship.guardian_user_id,populate_existing=True)
    if relationship.learner_id!=learner_id or relationship.state!='active' or relationship.valid_from>today or (relationship.valid_until and relationship.valid_until<today) or relationship.information_rights not in {'full','allowed','yes'} or relationship.restrictions or not relationship.source_reference or not user or user.state!='active':raise DomainError('recipient_unresolved','Current information rights and reviewed source evidence are required for this guardian.',409)
    # Parental responsibility alone never establishes information rights.
    require_school_access(db,Actor(user.id),school_id)
    return encode({c.name:getattr(relationship,c.name) for c in relationship.__table__.columns})
def recipient_ready(db,actor,school_id,revision_id,learner_id,purpose,lock=False):
    revision=get(db,m.RecipientRevision,school_id,revision_id);row=get(db,m.RecipientClearance,school_id,revision.clearance_id)
    if row.learner_id!=learner_id:raise access_denied()
    binding=relationship_binding(db,school_id,learner_id,row.relationship_id,lock)
    if row.state!='active' or row.current_revision!=revision.number or revision.relationship_binding!=binding or digest({'settings':revision.settings,'relationship':binding})!=revision.digest:raise conflict('The guardian relationship changed after its explicit rights review.')
    settings_current(revision.settings)
    if purpose not in revision.settings['purposes']:raise conflict('This guardian clearance does not cover the exact purpose.')
    review=db.scalar(select(m.RecipientReview).where(m.RecipientReview.school_id==school_id,m.RecipientReview.revision_id==revision.id))
    if not review or review.digest!=revision.digest or not authority_current(db,school_id,review.reviewer_id,review.authority,learner_id):raise conflict('Guardian rights need a current authorized human review.')
    access(db,Actor(review.reviewer_id),school_id,learner_id,'communication.recipient.review');checked_sources(db,Actor(review.reviewer_id),school_id,revision.settings['sources'],learner_id)
    return revision,binding
@mutation('communication.recipient.manage','recipient')
def create_recipient(db,actor,school_id,command):
    learner=str(command.learner_id);binding=relationship_binding(db,school_id,learner,str(command.relationship_id));checked_sources(db,actor,school_id,command.settings.sources,learner);settings=command.settings.model_dump(mode='json');settings_current(settings)
    row=m.RecipientClearance(school_id=school_id,learner_id=learner,relationship_id=str(command.relationship_id),state='active');db.add(row);db.flush();db.add(m.RecipientRevision(school_id=school_id,clearance_id=row.id,number=1,settings=settings,relationship_binding=binding,digest=digest({'settings':settings,'relationship':binding}),author_id=actor.user_id));event(db,actor,row,'communication.recipient.created');return row
@mutation('communication.recipient.manage','recipient')
def change_recipient(db,actor,school_id,identity,command):
    row=get(db,m.RecipientClearance,school_id,identity,command.expected_version);binding=relationship_binding(db,school_id,row.learner_id,row.relationship_id);checked_sources(db,actor,school_id,command.settings.sources,row.learner_id);settings=command.settings.model_dump(mode='json');settings_current(settings)
    row.current_revision+=1;row.version+=1;row.state='active';db.add(m.RecipientRevision(school_id=school_id,clearance_id=row.id,number=row.current_revision,settings=settings,relationship_binding=binding,digest=digest({'settings':settings,'relationship':binding}),author_id=actor.user_id));event(db,actor,row,'communication.recipient.changed');return row
@mutation('communication.recipient.review','recipient')
def review_recipient(db,actor,school_id,identity,command):
    row=get(db,m.RecipientClearance,school_id,identity,command.expected_version);revision=current(db,row,m.RecipientRevision,'clearance_id');exact(row,revision,command);binding=relationship_binding(db,school_id,row.learner_id,row.relationship_id)
    if binding!=revision.relationship_binding:raise conflict('The guardian source changed before review.')
    checked_sources(db,actor,school_id,revision.settings['sources'],row.learner_id);settings_current(revision.settings);binding=authority(db,actor,school_id,'communication.recipient.review',row.learner_id)
    db.add(m.RecipientReview(school_id=school_id,revision_id=revision.id,digest=revision.digest,reviewer_id=actor.user_id,authority=binding,reason=command.reason));row.version+=1;event(db,actor,row,'communication.recipient.reviewed');return row
@mutation('communication.recipient.review','recipient')
def revoke_recipient(db,actor,school_id,identity,command):
    row=get(db,m.RecipientClearance,school_id,identity,command.expected_version);row.state='revoked';row.version+=1;event(db,actor,row,'communication.recipient.revoked');return row

def frozen(db,actor,school_id,learner_id,revision_id,purpose):return documents.frozen_revision(db,actor,school_id,learner_id,str(revision_id),purpose)
def render(content,keys=None):
    chosen=content['sections'] if keys is None else [v for v in content['sections'] if v['key'] in keys]
    return {'subject':content['subject'] or '', 'body':'\n\n'.join(v['text'] or '' for v in chosen)}
def make_revision(db,actor,row,selection):
    learner=row.learner_id;doc=frozen(db,actor,row.school_id,learner,selection.document_revision_id,selection.purpose)
    if not set(selection.section_keys)<={v['key'] for v in doc['content']['sections']}:raise conflict('Select exact authored sections of the approved document.')
    recipient,binding=recipient_ready(db,actor,row.school_id,str(selection.recipient_revision_id),learner,selection.purpose)
    if binding['id'] not in doc['recipient_relationship_ids']:raise conflict('The document review did not include this guardian relationship.')
    policy=channel_ready(db,actor,row.school_id,str(selection.channel_revision_id),selection.purpose,doc['kind'])
    if selection.attachments and not policy.settings['allow_attachments']:raise conflict('Attachments are outside the reviewed channel policy.')
    attachments=[]
    for chosen in selection.attachments:
        source=frozen(db,actor,row.school_id,learner,chosen.document_revision_id,selection.purpose)
        if binding['id'] not in source['recipient_relationship_ids']:raise conflict('Attachment source review does not include this guardian.')
        payload=render(source['content']);data=(payload['subject']+'\n\n'+payload['body']).encode('utf-8')
        if len(data)>500000:raise conflict('The approved attachment exceeds the bounded transport size.')
        attachments.append({'id':str(uuid4()),'filename':chosen.filename,'content_type':'text/plain; charset=utf-8','digest':hashlib.sha256(data).hexdigest(),'source_revision_id':source['revision_id'],'source_digest':source['revision_digest'],'snapshot_digest':source['snapshot_digest'],'data':data})
    manifest={'format':'spesped.recipient-package.v1','school_id':row.school_id,'learner_id':learner,'document_revision_id':doc['revision_id'],'document_digest':doc['revision_digest'],'snapshot_digest':doc['snapshot_digest'],'kind':doc['kind'],'period':doc['period'],'relationship_id':binding['id'],'guardian_user_id':binding['guardian_user_id'],'recipient_revision_id':recipient.id,'recipient_digest':recipient.digest,'purpose':selection.purpose,'channel_revision_id':policy.id,'channel_digest':policy.digest,'channel':policy.settings['channel'],'connection_key':policy.settings['connection_key'],'payload':render(doc['content'],selection.section_keys),'section_keys':selection.section_keys,'attachments':[{k:v for k,v in att.items() if k!='data'} for att in attachments]}
    content_digest=digest({'payload':manifest['payload'],'attachments':manifest['attachments']});revision=m.PackageRevision(school_id=row.school_id,package_id=row.id,number=row.current_revision,manifest=manifest,digest=digest(manifest),content_digest=content_digest,author_id=actor.user_id);db.add(revision);db.flush()
    for att in attachments:db.add(m.Attachment(school_id=row.school_id,id=att['id'],revision_id=revision.id,filename=att['filename'],content_type=att['content_type'],digest=att['digest'],data=att['data'],source_revision_id=att['source_revision_id']))
    return revision
@mutation('communication.write','package')
def create_package(db,actor,school_id,command):
    if command.corrects_dispatch_id:
        old=get(db,m.Dispatch,school_id,command.corrects_dispatch_id);prior=get(db,m.DisclosurePackage,school_id,old.package_id)
        if prior.learner_id!=str(command.selection.learner_id) or old.state not in {'accepted','unknown','failed'}:raise conflict('A correction must reference a historical dispatch for the same learner.')
    row=m.DisclosurePackage(school_id=school_id,learner_id=str(command.selection.learner_id),owner_id=actor.user_id,state='draft',corrects_dispatch_id=str(command.corrects_dispatch_id) if command.corrects_dispatch_id else None);db.add(row);db.flush();make_revision(db,actor,row,command.selection);event(db,actor,row,'communication.package.created');return row
@mutation('communication.write','package')
def change_package(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version)
    if row.state=='revoked':raise conflict('A revoked package cannot be amended; create a corrected package.')
    row.current_revision+=1;row.version+=1;row.state='draft';db.flush();make_revision(db,actor,row,command.selection);event(db,actor,row,'communication.package.changed');return row

def integrity(db,revision):
    manifest=revision.manifest
    if digest(manifest)!=revision.digest or digest({'payload':manifest['payload'],'attachments':manifest['attachments']})!=revision.content_digest:raise conflict('The retained exact package failed integrity validation.')
    attachments=list(db.scalars(select(m.Attachment).where(m.Attachment.school_id==revision.school_id,m.Attachment.revision_id==revision.id)))
    if {v.id for v in attachments}!={v['id'] for v in manifest['attachments']}:raise conflict('The exact attachment set changed.')
    for attachment in attachments:
        entry=next(v for v in manifest['attachments'] if v['id']==attachment.id)
        if hashlib.sha256(attachment.data).hexdigest()!=attachment.digest or any(getattr(attachment,k)!=entry[k] for k in ('digest','filename','content_type','source_revision_id')):raise conflict('The attachment bytes or metadata failed integrity validation.')
    return attachments

def package_ready(db,actor,row,revision,authorization=False,lock=False,current_sources=True):
    if row.state=='revoked' or row.current_revision!=revision.number:raise conflict('The selected package revision is revoked or superseded.')
    manifest=revision.manifest;attachments=integrity(db,revision)
    policy=channel_ready(db,actor,row.school_id,manifest['channel_revision_id'],manifest['purpose'],manifest['kind'])
    recipient,binding=recipient_ready(db,actor,row.school_id,manifest['recipient_revision_id'],row.learner_id,manifest['purpose'],lock)
    if policy.digest!=manifest['channel_digest'] or recipient.digest!=manifest['recipient_digest'] or binding['id']!=manifest['relationship_id'] or binding['guardian_user_id']!=manifest['guardian_user_id']:raise conflict('Recipient, purpose, or channel binding changed.')
    if current_sources:
        doc=frozen(db,actor,row.school_id,row.learner_id,manifest['document_revision_id'],manifest['purpose'])
        if doc['revision_digest']!=manifest['document_digest'] or doc['snapshot_digest']!=manifest['snapshot_digest'] or render(doc['content'],manifest['section_keys'])!=manifest['payload']:raise conflict('The source-approved exact payload changed.')
        for item in manifest['attachments']:
            source=frozen(db,actor,row.school_id,row.learner_id,item['source_revision_id'],manifest['purpose']);payload=render(source['content']);expected=(payload['subject']+'\n\n'+payload['body']).encode('utf-8')
            if source['revision_digest']!=item['source_digest'] or source['snapshot_digest']!=item['snapshot_digest'] or hashlib.sha256(expected).hexdigest()!=item['digest']:raise conflict('An attachment source approval changed.')
    if authorization:
        content=db.scalar(select(m.ContentReview).where(m.ContentReview.school_id==row.school_id,m.ContentReview.revision_id==revision.id));disclosure=db.scalar(select(m.RecipientAuthorization).where(m.RecipientAuthorization.school_id==row.school_id,m.RecipientAuthorization.revision_id==revision.id))
        if row.state!='authorized' or content is None or disclosure is None or content.content_digest!=revision.content_digest or disclosure.package_digest!=revision.digest:raise conflict('Exact content review and disclosure authorization are required.')
        for review,person in ((content,content.reviewer_id),(disclosure,disclosure.approver_id)):
            if not authority_current(db,row.school_id,person,review.authority,row.learner_id):raise conflict('A signer no longer holds the exact reviewed authority scope.')
            access(db,Actor(person),row.school_id,row.learner_id,review.authority['action'])
    return policy,attachments
@mutation('communication.content.review','package')
def review_content(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version);revision=current(db,row,m.PackageRevision,'package_id');exact(row,revision,command);package_ready(db,actor,row,revision)
    if row.state!='draft':raise conflict('Create a new package revision for another content review.')
    binding=authority(db,actor,school_id,'communication.content.review',row.learner_id);db.add(m.ContentReview(school_id=school_id,revision_id=revision.id,content_digest=revision.content_digest,reviewer_id=actor.user_id,authority=binding,reason=command.reason));row.state='content_reviewed';row.version+=1;event(db,actor,row,'communication.content.reviewed',revision_id=revision.id);return row
@mutation('communication.authorize','package')
def authorize_package(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version);revision=current(db,row,m.PackageRevision,'package_id');exact(row,revision,command);package_ready(db,actor,row,revision)
    review=db.scalar(select(m.ContentReview).where(m.ContentReview.school_id==school_id,m.ContentReview.revision_id==revision.id))
    if row.state!='content_reviewed' or review is None or review.content_digest!=revision.content_digest or not authority_current(db,school_id,review.reviewer_id,review.authority,row.learner_id):raise conflict('The exact current content requires human review before disclosure authorization.')
    binding=authority(db,actor,school_id,'communication.authorize',row.learner_id);db.add(m.RecipientAuthorization(school_id=school_id,revision_id=revision.id,package_digest=revision.digest,approver_id=actor.user_id,authority=binding,reason=command.reason));row.state='authorized';row.version+=1;event(db,actor,row,'communication.disclosure.authorized',revision_id=revision.id);return row
@mutation('communication.authorize','package')
def revoke_package(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version);row.state='revoked';row.version+=1;event(db,actor,row,'communication.package.revoked');return row
@mutation('communication.export','package')
def export_package(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version);revision=current(db,row,m.PackageRevision,'package_id');exact(row,revision,command);package_ready(db,actor,row,revision,authorization=True)
    db.add(m.ExportRecord(school_id=school_id,revision_id=revision.id,actor_id=actor.user_id,mode=command.mode,package_digest=revision.digest));row.version+=1;event(db,actor,row,'communication.package.'+command.mode,revision_id=revision.id,delivery_confirmed=False);return row
@mutation('communication.send','package')
def queue_dispatch(db,actor,school_id,identity,command):
    row=get(db,m.DisclosurePackage,school_id,identity,command.expected_version);revision=current(db,row,m.PackageRevision,'package_id');exact(row,revision,command);policy,_=package_ready(db,actor,row,revision,authorization=True,lock=True)
    registry=db.info.get('communication_transport_registry') or TransportRegistry();registry.resolve(school_id,policy.settings['channel'],policy.settings['connection_key'])
    dispatch=m.Dispatch(school_id=school_id,package_id=row.id,revision_id=revision.id,sender_id=actor.user_id,state='queued');db.add(dispatch);db.flush();row.version+=1;event(db,actor,row,'communication.dispatch.queued',dispatch_id=dispatch.id,revision_id=revision.id);return row

def dispatch_package(db,dispatch):return get(db,m.DisclosurePackage,dispatch.school_id,dispatch.package_id),get(db,m.PackageRevision,dispatch.school_id,dispatch.revision_id)
def dispatch_gate(db,actor,dispatch):
    row,revision=dispatch_package(db,dispatch);access(db,actor,row.school_id,row.learner_id,'communication.send');access(db,Actor(dispatch.sender_id),row.school_id,row.learner_id,'communication.send');policy,attachments=package_ready(db,actor,row,revision,authorization=True,lock=True)
    registry=db.info.get('communication_transport_registry') or TransportRegistry();binding=registry.binding(row.school_id,policy.settings['channel'],policy.settings['connection_key']);return row,revision,policy,attachments,registry,binding
@mutation('communication.send','dispatch')
def prepare_dispatch(db,actor,school_id,identity,command):
    dispatch=get(db,m.Dispatch,school_id,identity,command.expected_version,lock=True)
    if dispatch.state not in {'queued','failed'}:raise conflict('Unknown or started delivery must be reconciled before another submission.')
    row,revision,policy,_,registry,binding=dispatch_gate(db,actor,dispatch)
    attempt=m.DispatchAttempt(school_id=school_id,dispatch_id=dispatch.id,revision_id=revision.id,submission_key=str(uuid4()),provider_key=policy.settings['connection_key'] or 'native-portal',configuration_digest=binding,package_digest=revision.digest,sender_id=actor.user_id);db.add(attempt);db.flush();dispatch.latest_attempt_id=attempt.id;dispatch.provider_reference=None;dispatch.state='sending';dispatch.version+=1;event(db,actor,dispatch,'communication.dispatch.prepared',attempt_id=attempt.id,revision_id=revision.id);return dispatch

def envelope(db,revision,attempt):
    return {'protocol':PROTOCOL,'submission_key':attempt.submission_key,'package_digest':revision.digest,'recipient':{'user_id':revision.manifest['guardian_user_id']},'payload':revision.manifest['payload'],'attachments':[{'filename':v.filename,'content_type':v.content_type,'data_base64':base64.b64encode(v.data).decode('ascii')} for v in integrity(db,revision)]}
def append_receipt(db,actor,dispatch,attempt,outcome):
    dispatch.state='failed' if outcome.status=='not_found' else outcome.status;dispatch.provider_reference=outcome.provider_reference or dispatch.provider_reference;dispatch.version+=1
    db.add(m.DeliveryReceipt(school_id=dispatch.school_id,dispatch_id=dispatch.id,attempt_id=attempt.id,outcome=outcome.status,provider_reference=outcome.provider_reference,reason_code=outcome.reason_code));event(db,actor,dispatch,'communication.dispatch.'+outcome.status,attempt_id=attempt.id,reason_code=outcome.reason_code)
@mutation('communication.send','dispatch')
def mark_release(db,actor,school_id,identity,command):
    dispatch=get(db,m.Dispatch,school_id,identity,command.expected_version,lock=True)
    if dispatch.state!='sending':raise conflict('Only a prepared attempt can start release. Reconcile an unknown attempt.')
    dispatch_gate(db,actor,dispatch);attempt=get(db,m.DispatchAttempt,school_id,dispatch.latest_attempt_id)
    append_receipt(db,actor,dispatch,attempt,TransportOutcome('unknown',reason_code='release_started'));return dispatch

def release_dispatch(db,actor,school_id,identity,command):
    # A semantic replay returns the retained result and never crosses the wire.
    started=mark_release(db,actor,school_id,identity,command)
    # The replay decision is made inside the serialized command transaction.
    # A pre-lock lookup can race another release completing with unknown status.
    if db.info.get('communication_command_replayed',True):return started
    previous={k:db.info.get(k) for k in ('communication_request_key','communication_correlation_id')}
    db.info['communication_request_key']=command.request_key;db.info['communication_correlation_id']=str(uuid4())
    try:
        db.scalar(select(School.id).where(School.id==school_id).with_for_update());dispatch=get(db,m.Dispatch,school_id,identity,lock=True)
        if dispatch.state!='unknown' or dispatch.version!=started['version']:raise conflict('The delivery outcome changed before release.')
        attempt=get(db,m.DispatchAttempt,school_id,dispatch.latest_attempt_id)
        try:
            row,revision,policy,attachments,registry,binding=dispatch_gate(db,actor,dispatch)
            if binding!=attempt.configuration_digest:raise conflict('The configured transport changed after attempt preparation.')
        except DomainError:
            append_receipt(db,actor,dispatch,attempt,TransportOutcome('failed',reason_code='release_authorization_changed'));db.commit();return dispatch_view(db,actor,school_id,identity)
        # Rights row locks and the school command lock remain held across release.
        if policy.settings['channel']=='portal':
            grant=m.PortalAccessGrant(school_id=school_id,dispatch_id=dispatch.id,revision_id=revision.id,guardian_user_id=revision.manifest['guardian_user_id'],expires_at=utcnow()+timedelta(hours=policy.settings['portal_lifetime_hours']),state='active');db.add(grant);db.flush();outcome=TransportOutcome('accepted','portal:'+grant.id,'portal_published')
        else:outcome=registry.resolve(school_id,policy.settings['channel'],policy.settings['connection_key']).call(envelope(db,revision,attempt))
        # Completion metadata is a fact even when later authority changes.
        append_receipt(db,actor,dispatch,attempt,outcome);db.commit();return dispatch_view(db,actor,school_id,identity)
    except Exception:db.rollback();raise
    finally:
        for k,v in previous.items():
            if v is None:db.info.pop(k,None)
            else:db.info[k]=v

@mutation('communication.reconcile','dispatch')
def reconcile_dispatch(db,actor,school_id,identity,command):
    dispatch=get(db,m.Dispatch,school_id,identity,command.expected_version,lock=True)
    if dispatch.state not in {'sending','unknown'}:raise conflict('Only an uncertain or interrupted attempt requires reconciliation.')
    row,revision=dispatch_package(db,dispatch);attempt=get(db,m.DispatchAttempt,school_id,dispatch.latest_attempt_id);integrity(db,revision);manifest=revision.manifest
    # Status reconciliation cannot release content and stays available after rights/source recall.
    registry=db.info.get('communication_transport_registry') or TransportRegistry();binding=registry.binding(school_id,manifest['channel'],manifest['connection_key'])
    if binding!=attempt.configuration_digest:raise conflict('Restore the original configured transport before reconciling this exact submission.')
    if manifest['channel']=='portal':
        grant=db.scalar(select(m.PortalAccessGrant).where(m.PortalAccessGrant.school_id==school_id,m.PortalAccessGrant.dispatch_id==dispatch.id))
        outcome=TransportOutcome('accepted','portal:'+grant.id,'portal_publication_reconciled') if grant else TransportOutcome('not_found',reason_code='portal_publication_absent')
    else:outcome=registry.resolve(school_id,manifest['channel'],manifest['connection_key']).call({'submission_key':attempt.submission_key,'package_digest':attempt.package_digest},reconcile=True)
    append_receipt(db,actor,dispatch,attempt,outcome);return dispatch

def portal_access(db,actor,school_id,grant,session_id,require_bound=True):
    require_school_access(db,actor,school_id)
    session=db.get(LoginSession,str(session_id),populate_existing=True) if session_id else None
    if not session or session.user_id!=actor.user_id or session.revoked_at is not None or session.expires_at<=utcnow() or actor.user_id!=grant.guardian_user_id or grant.state!='active' or grant.expires_at<=utcnow():raise access_denied()
    if require_bound and db.scalar(select(m.PortalSessionGrant.id).where(m.PortalSessionGrant.school_id==school_id,m.PortalSessionGrant.grant_id==grant.id,m.PortalSessionGrant.session_id==session.id)) is None:raise access_denied()
    dispatch=get(db,m.Dispatch,school_id,grant.dispatch_id);row,revision=dispatch_package(db,dispatch)
    if dispatch.state!='accepted' or revision.id!=grant.revision_id or revision.manifest['guardian_user_id']!=actor.user_id:raise access_denied()
    # The guardian never acquires dossier/source-read permissions. The package
    # owner checks the source through its existing staff access on every read.
    package_ready(db,Actor(row.owner_id),row,revision,authorization=True)
    return row,revision,session
@mutation('portal.open','portal')
def open_portal(db,actor,school_id,identity,command):
    grant=get(db,m.PortalAccessGrant,school_id,identity,command.expected_version);_,_,session=portal_access(db,actor,school_id,grant,db.info.get('communication_session_id'),require_bound=False)
    if db.scalar(select(m.PortalSessionGrant.id).where(m.PortalSessionGrant.school_id==school_id,m.PortalSessionGrant.grant_id==grant.id,m.PortalSessionGrant.session_id==session.id)) is None:db.add(m.PortalSessionGrant(school_id=school_id,grant_id=grant.id,session_id=session.id))
    grant.version+=1;event(db,actor,grant,'communication.portal.session_bound');return grant
@mutation('portal.read','portal')
def acknowledge_portal_read(db,actor,school_id,identity,command):
    grant=get(db,m.PortalAccessGrant,school_id,identity,command.expected_version);_,revision,session=portal_access(db,actor,school_id,grant,db.info.get('communication_session_id'))
    if db.scalar(select(m.PortalReadReceipt.id).where(m.PortalReadReceipt.school_id==school_id,m.PortalReadReceipt.grant_id==grant.id,m.PortalReadReceipt.session_id==session.id)) is None:db.add(m.PortalReadReceipt(school_id=school_id,grant_id=grant.id,session_id=session.id,guardian_user_id=actor.user_id,revision_id=revision.id))
    grant.version+=1;event(db,actor,grant,'communication.portal.read_acknowledged',revision_id=revision.id);return grant
@mutation('communication.authorize','portal')
def revoke_portal(db,actor,school_id,identity,command):
    grant=get(db,m.PortalAccessGrant,school_id,identity,command.expected_version);grant.state='revoked';grant.version+=1;event(db,actor,grant,'communication.portal.revoked');return grant

def public_payload(db,revision,include_bytes=False):
    attachments=integrity(db,revision)
    return {**revision.manifest['payload'],'attachments':[{'id':v.id,'filename':v.filename,'content_type':v.content_type,'size_bytes':len(v.data),**({'data_base64':base64.b64encode(v.data).decode('ascii')} if include_bytes else {})} for v in attachments]}
@read_contract
def preview(db,actor,school_id,identity):
    row=get(db,m.DisclosurePackage,school_id,identity);access(db,actor,school_id,row.learner_id,'communication.read');revision=current(db,row,m.PackageRevision,'package_id');package_ready(db,actor,row,revision)
    return public_payload(db,revision)
@read_contract
def staff_attachment(db,actor,school_id,identity,attachment_id):
    row=get(db,m.DisclosurePackage,school_id,identity);access(db,actor,school_id,row.learner_id,'communication.read');revision=current(db,row,m.PackageRevision,'package_id');_,attachments=package_ready(db,actor,row,revision)
    attachment=next((v for v in attachments if v.id==str(attachment_id)),None)
    if attachment is None:raise access_denied()
    return attachment.data,attachment.filename,attachment.content_type
@read_contract
def portal_payload(db,actor,school_id,identity):
    grant=get(db,m.PortalAccessGrant,school_id,identity);_,revision,_=portal_access(db,actor,school_id,grant,db.info.get('communication_session_id'));return public_payload(db,revision)
@read_contract
def portal_attachment(db,actor,school_id,identity,attachment_id):
    grant=get(db,m.PortalAccessGrant,school_id,identity);_,revision,_=portal_access(db,actor,school_id,grant,db.info.get('communication_session_id'));attachments=integrity(db,revision);attachment=next((v for v in attachments if v.id==str(attachment_id)),None)
    if attachment is None:raise access_denied()
    return attachment.data,attachment.filename,attachment.content_type

def channel_view(db,actor,school_id,identity):
    school_access(db,actor,school_id,'communication.policy.read');row=get(db,m.ChannelPolicy,school_id,identity);revision=current(db,row,m.ChannelRevision,'policy_id')
    recorded=bool(db.scalar(select(m.ChannelReview.id).where(m.ChannelReview.school_id==school_id,m.ChannelReview.revision_id==revision.id)));state='review_required'
    if recorded:
        try:channel_ready(db,actor,school_id,revision.id);state='reviewed_current'
        except DomainError:pass
    return {**row_json(row),'revision_id':revision.id,'content_digest':revision.digest,'settings':revision.settings,'review_recorded':recorded,'reviewed':state=='reviewed_current','review_state':state}
def recipient_view(db,actor,school_id,identity):
    row=get(db,m.RecipientClearance,school_id,identity);access(db,actor,school_id,row.learner_id,'communication.read');revision=current(db,row,m.RecipientRevision,'clearance_id')
    recorded=bool(db.scalar(select(m.RecipientReview.id).where(m.RecipientReview.school_id==school_id,m.RecipientReview.revision_id==revision.id)));state='review_required'
    if recorded:
        try:recipient_ready(db,actor,school_id,revision.id,row.learner_id,revision.settings['purposes'][0]);state='reviewed_current'
        except DomainError:pass
    return {**row_json(row),'revision_id':revision.id,'content_digest':revision.digest,'settings':revision.settings,'review_recorded':recorded,'reviewed':state=='reviewed_current','review_state':state}
def package_view(db,actor,school_id,identity):
    row=get(db,m.DisclosurePackage,school_id,identity);access(db,actor,school_id,row.learner_id,'communication.read');revision=current(db,row,m.PackageRevision,'package_id')
    state='current'
    try:package_ready(db,actor,row,revision)
    except DomainError:state='review_required'
    dispatches=[row_json(v) for v in db.scalars(select(m.Dispatch).where(m.Dispatch.school_id==school_id,m.Dispatch.package_id==row.id).order_by(m.Dispatch.created_at))]
    exports=[row_json(v) for v in db.scalars(select(m.ExportRecord).where(m.ExportRecord.school_id==school_id,m.ExportRecord.revision_id==revision.id))]
    # Staff can inspect exact identifiers/status even if current source rights
    # withhold the historical user-facing content.
    return {**row_json(row),'revision_id':revision.id,'content_digest':revision.digest,'payload_digest':revision.content_digest,'source_status':state,'payload':public_payload(db,revision) if state=='current' else None,'selection':{k:revision.manifest[k] for k in ('document_revision_id','recipient_revision_id','channel_revision_id','purpose','section_keys')},'dispatches':dispatches,'exports':exports,'automatic_send':False}
def dispatch_view(db,actor,school_id,identity):
    dispatch=get(db,m.Dispatch,school_id,identity);row,revision=dispatch_package(db,dispatch);access(db,actor,school_id,row.learner_id,'communication.read')
    attempts=[row_json(v) for v in db.scalars(select(m.DispatchAttempt).where(m.DispatchAttempt.school_id==school_id,m.DispatchAttempt.dispatch_id==dispatch.id).order_by(m.DispatchAttempt.created_at))]
    receipts=[row_json(v) for v in db.scalars(select(m.DeliveryReceipt).where(m.DeliveryReceipt.school_id==school_id,m.DeliveryReceipt.dispatch_id==dispatch.id).order_by(m.DeliveryReceipt.created_at,m.DeliveryReceipt.id))]
    grants=[row_json(v) for v in db.scalars(select(m.PortalAccessGrant).where(m.PortalAccessGrant.school_id==school_id,m.PortalAccessGrant.dispatch_id==dispatch.id))]
    reads=[row_json(v) for v in db.scalars(select(m.PortalReadReceipt).join(m.PortalAccessGrant,m.PortalAccessGrant.id==m.PortalReadReceipt.grant_id).where(m.PortalReadReceipt.school_id==school_id,m.PortalAccessGrant.dispatch_id==dispatch.id))]
    return {**row_json(dispatch),'attempts':attempts,'receipts':receipts,'portal_grants':grants,'read_receipts':reads,'transport_accepted':dispatch.state=='accepted','read_acknowledged':bool(reads),'acceptance_means_read':False}
def portal_view(db,actor,school_id,identity):
    grant=get(db,m.PortalAccessGrant,school_id,identity)
    membership=require_school_access(db,actor,school_id)
    if actor.user_id==grant.guardian_user_id:
        portal_access(db,actor,school_id,grant,db.info.get('communication_session_id'),require_bound=False)
        return {k:v for k,v in row_json(grant).items() if k in {'id','version','state','created_at','expires_at'}}
    dispatch=get(db,m.Dispatch,school_id,grant.dispatch_id);row,_=dispatch_package(db,dispatch);access(db,actor,school_id,row.learner_id,'communication.read');return row_json(grant)
def view(db,actor,school_id,kind,identity):return {'channel':channel_view,'recipient':recipient_view,'package':package_view,'dispatch':dispatch_view,'portal':portal_view}[kind](db,actor,school_id,identity)
@read_contract
def read(db,actor,school_id,kind,identity):return view(db,actor,school_id,kind,identity)
@read_contract
def list_items(db,actor,school_id,kind,learner_id=None,offset=0,limit=50):
    if kind=='portal':
        require_school_access(db,actor,school_id);rows=list(db.scalars(select(m.PortalAccessGrant).where(m.PortalAccessGrant.school_id==school_id,m.PortalAccessGrant.guardian_user_id==actor.user_id,m.PortalAccessGrant.state=='active',m.PortalAccessGrant.expires_at>utcnow()).order_by(m.PortalAccessGrant.created_at.desc())))
        values=[]
        for row in rows:
            try:values.append(portal_view(db,actor,school_id,row.id))
            except DomainError:continue
        return {'items':values[offset:offset+limit],'total':len(values)}
    if kind=='channel':
        school_access(db,actor,school_id,'communication.policy.read');model=m.ChannelPolicy;query=select(model).where(model.school_id==school_id)
    else:
        if learner_id is None:raise DomainError('learner_required','Select an authorized learner before listing communication.',422)
        learner_id=str(learner_id);access(db,actor,school_id,learner_id,'communication.read');model={'package':m.DisclosurePackage,'recipient':m.RecipientClearance,'dispatch':m.Dispatch}[kind]
        query=select(model).where(model.school_id==school_id)
        if kind=='dispatch':query=query.join(m.DisclosurePackage,model.package_id==m.DisclosurePackage.id).where(m.DisclosurePackage.learner_id==learner_id)
        else:query=query.where(model.learner_id==learner_id)
    rows=list(db.scalars(query.order_by(model.created_at.desc(),model.id)))
    return {'items':[view(db,actor,school_id,kind,v.id) for v in rows[offset:offset+limit]],'total':len(rows)}
@read_contract
def package_history(db,actor,school_id,identity,offset=0,limit=50):
    row=get(db,m.DisclosurePackage,school_id,identity);access(db,actor,school_id,row.learner_id,'communication.read');rows=list(db.scalars(select(m.PackageRevision).where(m.PackageRevision.school_id==school_id,m.PackageRevision.package_id==row.id).order_by(m.PackageRevision.number)))
    return {'items':[{'id':v.id,'number':v.number,'digest':v.digest,'created_at':v.created_at,'current':v.number==row.current_revision,'content_reviewed':bool(db.scalar(select(m.ContentReview.id).where(m.ContentReview.revision_id==v.id))),'disclosure_authorized':bool(db.scalar(select(m.RecipientAuthorization.id).where(m.RecipientAuthorization.revision_id==v.id)))} for v in rows[offset:offset+limit]],'total':len(rows)}
