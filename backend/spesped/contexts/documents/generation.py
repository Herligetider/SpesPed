"""Typed local-model proposals bound to exact current authorized document bases."""
import json
from spesped.auth import Actor
from spesped.contexts.identity.models import School
from sqlalchemy import select
from spesped.errors import DomainError,access_denied
from spesped.auth import require_authority
from spesped.contexts.platform import service as gateway
from spesped.contexts.platform.contracts import SourceInput,SourceRef,GenerationRequest,release_schema
from . import service as svc,models as m,schemas as s,adapters as a

def load_basis(db,actor,school_id,identity,action='documents.write'):
    snap=svc.get(db,m.EvidenceSnapshot,school_id,identity);row=svc.get(db,m.DocumentCase,school_id,snap.document_id)
    svc.access(db,actor,school_id,row.learner_id,action)
    # A snapshot is unique to a revision except generated selection revisions,
    # which deliberately carry the same frozen factual basis.
    rev=db.scalar(select(m.DocumentRevision).where(m.DocumentRevision.school_id==school_id,m.DocumentRevision.document_id==row.id,m.DocumentRevision.snapshot_id==snap.id).order_by(m.DocumentRevision.number).limit(1))
    if rev is None:raise access_denied()
    return row,rev,snap

def require_basis(db,actor,row,rev,snap):
    # No recursion through generated revisions: original basis revisions carry no
    # model lineage. The immutable snapshot itself contains only owner sources.
    _,status=svc.snapshot_status(db,actor,row,rev)
    if status['state']!='current':raise svc.conflict('New or changed basis requires a fresh document revision before generation.')

def resolve_generation_source(db,actor,school_id,learner_id,purpose,reference):
    if purpose not in {'report_drafting','guardian_email_drafting'} or reference.kind!='document_basis' or reference.revision!=1:raise access_denied()
    # Resolver may execute with a caller Session retaining staged changes.
    with a.owner_reader(db) as reader:
        configure_owner_sources(reader,db.info.get('ai_gateway_runtime') or db.info.get('documents_runtime'))
        row,rev,snap=load_basis(reader,actor,school_id,str(reference.source_id))
        if row.learner_id!=learner_id or (purpose=='guardian_email_drafting')!=(row.kind=='guardian_email'):raise access_denied()
        require_basis(reader,actor,row,rev,snap)
        body={'basis':snap.content,'document_sections':[{'key':v['key'],'text':v['text']} for v in rev.content['sections']],'limits':'Draft only. Cite factual source references; future plans never become completed activity. Missing evidence is not progress. No rights, grades, approval or dispatch.'}
        return SourceInput(reference,school_id,learner_id,purpose,json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False),provenance='school_data')

def request_suggestion(db,actor,school_id,identity,command,runtime):
    row=svc.get(db,m.DocumentCase,school_id,identity,command.expected_version);svc.access(db,actor,school_id,row.learner_id,'documents.write');rev=svc.current(db,row)
    if row.state in {'approved','discarded'} or rev.id!=str(command.revision_id):raise svc.conflict()
    snap=svc.get(db,m.EvidenceSnapshot,school_id,rev.snapshot_id);require_basis(db,actor,row,rev,snap)
    purpose='guardian_email_drafting' if row.kind=='guardian_email' else 'report_drafting'
    return gateway.create_job(db,actor,school_id,GenerationRequest(learner_id=row.learner_id,purpose=purpose,policy_id=command.policy_id,release_id=command.release_id,logical_request_key=command.request_key,sources=[SourceRef(kind='document_basis',source_id=snap.id,revision=1)]),runtime)
def proposal_digest(job):return a.digest({'job_id':job.id,'source_manifest':job.source_manifest,'release_digest':job.release_digest,'policy_version':job.policy_version,'output':job.output})
def proposal(db,actor,school_id,identity,job_id,runtime):
    row=svc.get(db,m.DocumentCase,school_id,identity);svc.access(db,actor,school_id,row.learner_id,'documents.write');rev=svc.current(db,row)
    job=gateway.current_job(db,actor,school_id,str(job_id),runtime,lock=True)
    purpose='guardian_email_drafting' if row.kind=='guardian_email' else 'report_drafting'
    expected=[{'kind':'document_basis','source_id':rev.snapshot_id,'revision':1}]
    if job.purpose!=purpose or job.learner_id!=row.learner_id or [v['reference'] for v in job.source_manifest]!=expected:raise access_denied()
    if job.state!='succeeded' or job.output is None:raise DomainError('suggestion_unavailable','No usable AI text is available. The editable manual document remains available.',409)
    snap=svc.get(db,m.EvidenceSnapshot,school_id,rev.snapshot_id);require_basis(db,actor,row,rev,snap)
    output=release_schema('document-draft.v1').model_validate({k:v for k,v in job.output.items() if k not in {'unconfirmed','requires_human_review','schema_version'}}).model_dump(mode='json')
    keys={v['key'] for v in rev.content['sections']}
    if any(v['key'] not in keys for v in output['sections']):raise DomainError('proposal_section_scope','The model suggested a section outside this exact document template.',409)
    return row,rev,snap,job,output
@svc.read_contract
def diff(db,actor,school_id,identity,job_id,runtime):
    row,rev,snap,job,output=proposal(db,actor,school_id,identity,job_id,runtime)
    return {'document_id':row.id,'revision_id':rev.id,'expected_version':row.version,'job_id':job.id,'proposal_digest':proposal_digest(job),'before':rev.content,'proposed':output,'source_manifest':job.source_manifest,'requires_human_review':True}
@svc.mutation('documents.write','document')
def apply(db,actor,school_id,identity,command):
    runtime=db.info.get('documents_runtime');row=svc.get(db,m.DocumentCase,school_id,identity,command.expected_version)
    row,rev,snap,job,output=proposal(db,actor,school_id,identity,command.job_id,runtime)
    if row.state in {'approved','discarded'} or rev.id!=str(command.revision_id) or command.proposal_digest!=proposal_digest(job):raise svc.conflict()
    if db.scalar(select(m.ProposalReview.id).where(m.ProposalReview.school_id==school_id,m.ProposalReview.job_id==job.id)):raise svc.conflict('This proposal already has a human selection outcome.')
    old=rev
    if command.outcome=='applied':
        if not command.selected_sections and not command.select_subject:raise DomainError('proposal_selection','Select at least one proposed section or subject.',422)
        content=s.Content.model_validate(rev.content).model_dump(mode='json');proposed={v['key']:v for v in output['sections']};bykey={v['key']:v for v in content['sections']}
        lineage=dict(rev.lineage);binding={'job_id':job.id,'basis_id':snap.id,'proposal_digest':proposal_digest(job)}
        for key in command.selected_sections:
            if key not in proposed:raise DomainError('proposal_selection','Choose a section present in this exact typed proposal.',422)
            section=proposed[key];bykey[key]['text']=section['text'];bykey[key]['missing_inputs']=list(dict.fromkeys(section['missing_evidence']+output['missing_evidence']))
            # Gateway citation binds the entire authorized basis; the internal
            # source manifest remains visible for human factual review.
            bykey[key]['source_keys']=[v['key'] for v in snap.content['entries'] if v['classification']!='future_plan_not_actual']
            lineage[key]=binding
        if command.select_subject:
            if output['subject'] is None:raise DomainError('proposal_selection','No proposed subject is available.',422)
            content['subject']=output['subject'];lineage['subject']=binding
        data=s.DocumentCreate.model_validate({**rev.configuration,'request_key':'ai-selected','content':content})
        row.current_revision+=1;row.version+=1;row.state='draft';db.flush()
        rev=svc.make_revision(db,actor,row,data,command.reason,lineage=lineage,existing_snapshot=snap)
    db.add(m.ProposalReview(school_id=school_id,document_id=row.id,revision_id=rev.id,job_id=job.id,proposal_digest=command.proposal_digest,outcome=command.outcome,selection={'sections':command.selected_sections,'subject':command.select_subject},reviewer_id=actor.user_id,reason=command.reason));svc.event(db,actor,row,'documents.suggestion.reviewed',job_id=job.id,outcome=command.outcome);return row

def validate_lineage(db,actor,row,rev,*,consumer_action='documents.read'):
    """Validate selected derivative provenance under its consumer's own scope.

    Reading a human-selected document is not another generation request. The
    gateway metadata port checks processing currency without returning output;
    source owner reads independently check this actual reader's permissions.
    """
    if consumer_action not in {'documents.read','documents.contribute'}:raise access_denied()
    svc.access(db,actor,row.school_id,row.learner_id,consumer_action)
    fields=None
    if consumer_action=='documents.contribute':
        fields=set(db.scalars(select(m.ContributionAssignment.section_key).where(
            m.ContributionAssignment.school_id==row.school_id,
            m.ContributionAssignment.revision_id==rev.id,
            m.ContributionAssignment.contributor_id==actor.user_id)))
        if not fields:raise access_denied()
    return _lineage_dependencies(db,actor,row,rev,consumer_action,fields,{rev.id})

def _lineage_dependencies(db,actor,row,rev,consumer_action,fields,seen):
    needs_review=False;checked=set()
    for field,binding in rev.lineage.items():
        if fields is not None and field not in fields:continue
        token=(binding['basis_id'],binding['job_id'])
        review=db.scalar(select(m.ProposalReview).where(
            m.ProposalReview.school_id==row.school_id,
            m.ProposalReview.document_id==row.id,
            m.ProposalReview.job_id==binding['job_id'],
            m.ProposalReview.proposal_digest==binding['proposal_digest'],
            m.ProposalReview.outcome=='applied'))
        if review is None:raise svc.conflict('The selected text has no exact immutable human selection record.')
        selected=svc.get(db,m.DocumentRevision,row.school_id,review.revision_id)
        if selected.document_id!=row.id or selected.snapshot_id!=binding['basis_id']:raise access_denied()
        if field=='subject':permitted=review.selection['subject']
        else:permitted=field in review.selection['sections']
        if not permitted:raise svc.conflict('The saved field is not part of the exact reviewed selection.')
        if token in checked:continue
        checked.add(token)
        runtime=db.info.get('documents_runtime') or db.info.get('ai_gateway_runtime')
        if not gateway.job_binding_is_current(db,row.school_id,binding['job_id'],runtime):
            raise DomainError('generation_processing_changed','The selected AI processing policy or reviewed release requires renewed review.',409)
        snapshot=svc.get(db,m.EvidenceSnapshot,row.school_id,binding['basis_id'])
        if snapshot.document_id!=row.id or snapshot.learner_id!=row.learner_id:raise access_denied()
        original=db.scalar(select(m.DocumentRevision).where(
            m.DocumentRevision.school_id==row.school_id,
            m.DocumentRevision.document_id==row.id,
            m.DocumentRevision.snapshot_id==snapshot.id).order_by(m.DocumentRevision.number).limit(1))
        if original is None or original.id in seen:raise svc.conflict('Cyclic or missing original generation provenance is unavailable.')
        # This never returns original document prose. It rechecks every original
        # source through its owning context using the current consumer actor.
        _,status=svc.snapshot_dependencies(db,actor,row,original,consumer_action)
        needs_review|=status['state']!='current'
        needs_review|=_lineage_dependencies(db,actor,row,original,consumer_action,None,seen|{original.id})
    return needs_review

def configured_generation(db,actor,school_id,learner_id,policy_id,release_id,runtime):
    """Owner platform configuration validation; never execute or commit here."""
    if runtime is None:raise DomainError('generation_runtime_unavailable','Local generation is unavailable; keep the editable manual draft.',503)
    with a.owner_reader(db) as reader:
        return gateway.validate_generation_configuration(reader,actor,school_id,learner_id,'guardian_email_drafting',str(policy_id),str(release_id),runtime)

def scheduled_binding(db,request,runtime):
    row=svc.get(db,m.DocumentCase,request.school_id,request.document_id);actor=Actor(request.owner_id)
    svc.access(db,actor,row.school_id,row.learner_id,'documents.write')
    run=svc.get(db,m.DraftRun,row.school_id,request.run_id);plan_revision=svc.get(db,m.ScheduleRevision,row.school_id,run.schedule_revision_id);plan=svc.get(db,m.EmailDraftSchedule,row.school_id,plan_revision.schedule_id)
    if plan_revision.settings.get('timezone')!=db.get(School,row.school_id).timezone:raise DomainError('schedule_timezone_changed','The school timezone changed after the frozen draft period was resolved.',409)
    if plan.current_revision!=plan_revision.number or plan.owner_id!=request.owner_id or plan.state not in {'active','ended'} or (plan.state=='ended' and plan.pause_reason!='natural_schedule_end'):raise DomainError('schedule_changed','The originating draft plan changed, paused or ended; review its pending generation request.',409)
    revision=svc.current(db,row)
    if revision.id!=request.revision_id or revision.snapshot_id!=request.snapshot_id or row.state in {'approved','discarded'}:raise svc.conflict('The scheduled document was edited or reviewed before generation completed.')
    snapshot=svc.get(db,m.EvidenceSnapshot,row.school_id,request.snapshot_id);require_basis(db,actor,row,revision,snapshot)
    configuration=configured_generation(db,actor,row.school_id,row.learner_id,request.policy_id,request.release_id,runtime)
    if configuration!=request.configuration_binding:raise DomainError('generation_configuration_changed','The selected processing policy or release changed after this exact draft request.',409)
    return actor,row,revision,snapshot

def _request_outcome(factory,school_id,request_id,state,reason,job_id=None,*,runtime=None,revalidate=False):
    from uuid import uuid4
    with factory() as db:
        db.scalar(select(School.id).where(School.id==school_id).with_for_update())
        request=db.scalar(select(m.ScheduledGenerationRequest).where(m.ScheduledGenerationRequest.school_id==school_id,m.ScheduledGenerationRequest.id==str(request_id)).with_for_update().execution_options(populate_existing=True))
        if request is None:raise access_denied()
        if revalidate:
            configure_owner_sources(db,runtime)
            try:scheduled_binding(db,request,runtime)
            except DomainError as exc:state='blocked';reason=exc.code
        # A late worker cannot regress a succeeded result or its stable job ID.
        if request.state=='succeeded' and state in {'pending','queued','running'}:return svc.row_json(request)
        if request.job_id and job_id and request.job_id!=job_id:raise svc.conflict('A request cannot bind two gateway jobs.')
        request.state=state;request.reason_code=reason;request.job_id=job_id or request.job_id;request.version+=1
        db.info['documents_request_key']=request.logical_key;db.info['documents_correlation_id']=str(uuid4())
        from spesped.auth import Actor
        svc.event(db,Actor(request.owner_id),request,'documents.scheduled_generation.'+state,job_id=request.job_id,reason_code=reason)
        result=svc.row_json(request);db.commit();return result

def process_scheduled_generation(factory,school_id,request_id,runtime,*,execute=True,retry_failed=False):
    """Real J26 worker callable, durable across process restarts and lost replies.

    The request and outbox are already committed with the draft. Gateway calls
    use their own transaction and a stable logical key. Repeating this processor
    reconciles the same job; it cannot create another draft or apply model text.
    """
    job=None
    try:
        with factory() as db:
            request=svc.get(db,m.ScheduledGenerationRequest,school_id,request_id)
            configure_owner_sources(db,runtime)
            actor,row,revision,snapshot=scheduled_binding(db,request,runtime)
            command=GenerationRequest(learner_id=row.learner_id,purpose='guardian_email_drafting',policy_id=request.policy_id,release_id=request.release_id,logical_request_key=request.logical_key,sources=[SourceRef(kind='document_basis',source_id=snapshot.id,revision=1)])
            # Even a previously succeeded request rechecks source/owner/config
            # before exposing its completion state on a later worker replay.
            job=gateway.create_job(db,actor,school_id,command,runtime)
        if execute and (job.state=='queued' or (retry_failed and job.state in {'failed','unavailable'})):
            try:job=gateway.run_job(factory,None,school_id,job.id,job.version,runtime)
            except DomainError as exc:
                if exc.status_code!=409:raise
                with factory() as db:job=gateway.current_job(db,actor,school_id,job.id,runtime)
        state={'unavailable':'failed','cancelled':'failed'}.get(job.state,job.state)
        return _request_outcome(factory,school_id,request_id,state,job.error_code,job.id,runtime=runtime,revalidate=True)
    except DomainError as exc:
        return _request_outcome(factory,school_id,request_id,'failed' if exc.status_code==429 else 'blocked',exc.code,job.id if job else None)
    except Exception:
        # A lost acknowledgement is not a failed/new request. Replaying its
        # logical key reconciles any already committed gateway job first.
        return _request_outcome(factory,school_id,request_id,'pending','gateway_reply_unknown',job.id if job else None)


def configure_owner_sources(db,runtime):
    # Background gateway sessions do not pass through HTTP dependency wiring.
    # Reconstruct the same native source ports on this owned reader/session.
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    from spesped.contexts.administration.adapters import NativeAssessmentAuthorityPort,NativeQualificationReadPort
    db.info['documents_runtime']=runtime;db.info['plans_runtime']=runtime;db.info['teaching_runtime']=runtime
    if db.info.get('curriculum_source_port') is None:db.info['curriculum_source_port']=EvidenceSourceReadPort(getattr(getattr(runtime,'source_resolver',None),'storage',None))
    if db.info.get('assessment_authority_port') is None:db.info['assessment_authority_port']=NativeAssessmentAuthorityPort()
    if db.info.get('teaching_qualification_port') is None:db.info['teaching_qualification_port']=NativeQualificationReadPort()
