from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor, get_actor, require_learner_access
from spesped.audit import record_audit
from spesped.db import get_db
from spesped.errors import DomainError
from . import service
from .common import commit, mutate, source_status, authorized_projection
from .models import SupportCase, EducationConsent, Referral, ReferralRevision, ReferralContact, ExpertAssessment, Recommendation, EducationDecision, DecisionRevision, DecisionProvision
from .schemas import CreateCase, CaseUpdate, ConsentInput, Reason, CreateReferral, ReviseReferral, ExactReview, ContactInput, AssessmentInput, DecisionInput, DecisionUpdate, ClarificationInput, ResolveClarification

router=APIRouter(prefix='/api/v1/schools/{school_id}',tags=['support entitlements'])


def row_view(row):
    return {c.key:(str(getattr(row,c.key)) if isinstance(getattr(row,c.key),Decimal) else getattr(row,c.key)) for c in row.__table__.columns}


def case_view(row):
    return row_view(row)


def consent_view(db,actor,row):
    return authorized_projection(db,actor,row.school_id,row.learner_id,row_view(row),[row.source],('source','purpose','representative','representative_capacity','revoked_reason'))


def referral_bindings(db,row,revision):
    bindings=list(revision.sources)
    ids=[revision.processing_basis_id,*revision.consent_ids,*revision.disclosure_permission_ids]
    for consent in db.scalars(select(EducationConsent).where(EducationConsent.school_id == row.school_id,EducationConsent.learner_id == row.learner_id,EducationConsent.case_id == row.case_id,EducationConsent.id.in_(ids))):
        bindings.append(consent.source)
    return bindings


def referral_view(db,actor,row,revision=None):
    value=row_view(row);revision=revision or service.referral_revision(db,row)
    bindings=referral_bindings(db,row,revision)
    projected=authorized_projection(db,actor,row.school_id,row.learner_id,{'content':row_view(revision)},bindings,('content',))
    value['source_status']=projected['source_status']
    value['content']=projected['content'] if projected['content'] is not None else {'id':revision.id,'revision':revision.revision,'digest':revision.digest,'issue':'source_review_required'}
    contacts=db.scalars(select(ReferralContact).where(ReferralContact.school_id == row.school_id,ReferralContact.referral_id == row.id).order_by(ReferralContact.recorded_at,ReferralContact.id)).all()
    value['contacts']=[]
    for contact in contacts:
        # A contact note can discuss the submitted referral as well as its own
        # receipt source. Planned follow-ups remain bound to that referral basis.
        recorded=db.scalar(select(ReferralRevision).where(ReferralRevision.school_id == row.school_id,ReferralRevision.referral_id == row.id,ReferralRevision.revision == contact.referral_revision))
        contact_bindings=referral_bindings(db,row,recorded)
        if contact.source:contact_bindings.append(contact.source)
        projected=authorized_projection(db,actor,row.school_id,row.learner_id,row_view(contact),contact_bindings,('recipient','external_reference','note','source'))
        value['contacts'].append(projected)
    return value


def assessment_view(db,actor,row):
    recommendations=db.scalars(select(Recommendation).where(Recommendation.school_id == row.school_id,Recommendation.assessment_id == row.id).order_by(Recommendation.id)).all()
    value=authorized_projection(db,actor,row.school_id,row.learner_id,row_view(row),[row.source]+[r.source for r in recommendations],('source','issuer'))
    value['recommendations']=[row_view(r) for r in recommendations] if value['source_status'] == 'current' else []
    value['authority']='expert_recommendation_only'
    return value


def clarification_view(db,actor,row):
    bindings=[row.source] if row.source else []
    if row.kind == 'recommendation_difference':
        from .provenance import comparison_bindings
        bindings=comparison_bindings(db,row)
        if bindings is None:
            value=row_view(row)
            value.update(description=None,source=None,resolution=None,comparison_basis=None,
                         source_status='review_required',comparison_basis_status='unknown')
            return value
    return authorized_projection(db,actor,row.school_id,row.learner_id,row_view(row),bindings,('description','source','resolution','comparison_basis'))


def decision_view(db,actor,row,revision=None):
    revision=revision or service.decision_revision(db,row)
    value=row_view(row);value['content']=row_view(revision)
    provisions=db.scalars(select(DecisionProvision).where(DecisionProvision.school_id == row.school_id,DecisionProvision.decision_revision_id == revision.id).order_by(DecisionProvision.clause)).all()
    value['source_status']=source_status(db,actor,row.school_id,row.learner_id,[revision.source]+[p.source for p in provisions])
    value['provisions']=[{**row_view(p),'decision_id':row.id,'decision_revision_id':revision.id} for p in provisions] if value['source_status'] == 'current' else []
    if value['source_status'] != 'current': value['content']={'id':revision.id,'revision':revision.revision,'state':revision.state,'issue':'source_review_required'}
    return value


def read_audit(db,actor,row):
    record_audit(db,actor,row.school_id,'support_case.read',row.__tablename__,row.id);commit(db)


@router.post('/learners/{learner_id}/support-cases',status_code=201)
def create_case(school_id:UUID,learner_id:UUID,command:CreateCase,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.create_case(db,actor,str(school_id),str(learner_id),command))
    # A creation receipt must not disclose later protected case edits when the
    # creator retries without independent case-read authority.
    return {'id':row.id,'learner_id':str(learner_id),'version':1,'state':'preparation','owner_id':str(command.owner_id),'concern':command.concern,'purpose':command.purpose}


@router.get('/learners/{learner_id}/support-cases')
def cases(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    require_learner_access(db,actor,str(school_id),str(learner_id),'support_case.access')
    rows=[]
    for row in db.scalars(select(SupportCase).where(SupportCase.school_id == str(school_id),SupportCase.learner_id == str(learner_id)).order_by(SupportCase.created_at,SupportCase.id)):
        try: service.case_access(db,actor,str(school_id),row.id)
        except DomainError as exc:
            if exc.status_code == 403: continue
            raise
        rows.append(row)
    record_audit(db,actor,str(school_id),'support_case.list_read','learner',str(learner_id));commit(db)
    return {'items':[case_view(r) for r in rows[offset:offset+limit]],'total':len(rows)}


@router.get('/support-cases/{case_id}')
def case(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=service.case_access(db,actor,str(school_id),str(case_id));read_audit(db,actor,row);return case_view(row)


@router.patch('/support-cases/{case_id}')
def update_case(school_id:UUID,case_id:UUID,command:CaseUpdate,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    return case_view(mutate(db,lambda:service.update_case(db,actor,str(school_id),str(case_id),command)))


@router.post('/support-cases/{case_id}/consents',status_code=201)
def consent(school_id:UUID,case_id:UUID,command:ConsentInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.create_consent(db,actor,str(school_id),str(case_id),command));return consent_view(db,actor,row)


@router.get('/support-cases/{case_id}/consents')
def consents(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    case=service.case_access(db,actor,str(school_id),str(case_id))
    rows=db.scalars(select(EducationConsent).where(EducationConsent.school_id == str(school_id),EducationConsent.case_id == case.id,EducationConsent.learner_id == case.learner_id).order_by(EducationConsent.created_at,EducationConsent.id)).all()
    value={'items':[consent_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    read_audit(db,actor,case);return value


@router.post('/support-cases/{case_id}/consents/{consent_id}/revoke')
def revoke(school_id:UUID,case_id:UUID,consent_id:UUID,command:Reason,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.revoke_consent(db,actor,str(school_id),str(case_id),str(consent_id),command));return consent_view(db,actor,row)


@router.post('/support-cases/{case_id}/referrals',status_code=201)
def referral(school_id:UUID,case_id:UUID,command:CreateReferral,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.save_referral(db,actor,str(school_id),str(case_id),command));return referral_view(db,actor,row)


@router.get('/support-cases/{case_id}/referrals')
def referrals(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    case=service.case_access(db,actor,str(school_id),str(case_id))
    rows=db.scalars(select(Referral).where(Referral.school_id == str(school_id),Referral.case_id == case.id,Referral.learner_id == case.learner_id).order_by(Referral.created_at,Referral.id)).all()
    value={'items':[referral_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    read_audit(db,actor,case);return value


@router.get('/support-cases/{case_id}/referrals/{referral_id}')
def get_referral(school_id:UUID,case_id:UUID,referral_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    _,row=service.child(db,actor,str(school_id),str(case_id),Referral,str(referral_id));read_audit(db,actor,row);return referral_view(db,actor,row)


@router.post('/support-cases/{case_id}/referrals/{referral_id}/revisions',status_code=201)
def revise_referral(school_id:UUID,case_id:UUID,referral_id:UUID,command:ReviseReferral,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.save_referral(db,actor,str(school_id),str(case_id),command,str(referral_id)));return referral_view(db,actor,row)


@router.post('/support-cases/{case_id}/referrals/{referral_id}/review')
def review_referral(school_id:UUID,case_id:UUID,referral_id:UUID,command:ExactReview,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.review_referral(db,actor,str(school_id),str(case_id),str(referral_id),command));return referral_view(db,actor,row)


@router.post('/support-cases/{case_id}/referrals/{referral_id}/contacts')
def contact(school_id:UUID,case_id:UUID,referral_id:UUID,command:ContactInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.contact_referral(db,actor,str(school_id),str(case_id),str(referral_id),command));return referral_view(db,actor,row)


@router.post('/support-cases/{case_id}/expert-assessments',status_code=201)
def assessment(school_id:UUID,case_id:UUID,command:AssessmentInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.import_assessment(db,actor,str(school_id),str(case_id),command));return assessment_view(db,actor,row)


@router.post('/support-cases/{case_id}/expert-assessments/{assessment_id}/confirm')
def confirm_assessment(school_id:UUID,case_id:UUID,assessment_id:UUID,command:Reason,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.confirm_assessment(db,actor,str(school_id),str(case_id),str(assessment_id),command));return assessment_view(db,actor,row)


@router.get('/support-cases/{case_id}/expert-assessments')
def assessments(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    case=service.case_access(db,actor,str(school_id),str(case_id))
    rows=db.scalars(select(ExpertAssessment).where(ExpertAssessment.school_id == str(school_id),ExpertAssessment.case_id == case.id).order_by(ExpertAssessment.assessment_at,ExpertAssessment.id)).all()
    value={'items':[assessment_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    read_audit(db,actor,case);return value


@router.post('/support-cases/{case_id}/decisions',status_code=201)
def decision(school_id:UUID,case_id:UUID,command:DecisionInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.save_decision(db,actor,str(school_id),str(case_id),command));return decision_view(db,actor,row)


@router.get('/support-cases/{case_id}/decisions')
def decisions(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    case=service.case_access(db,actor,str(school_id),str(case_id))
    rows=db.scalars(select(EducationDecision).where(EducationDecision.school_id == str(school_id),EducationDecision.case_id == case.id).order_by(EducationDecision.created_at,EducationDecision.id)).all()
    value={'items':[decision_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    read_audit(db,actor,case);return value


@router.get('/support-cases/{case_id}/decisions/{decision_id}')
def get_decision(school_id:UUID,case_id:UUID,decision_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    _,row=service.child(db,actor,str(school_id),str(case_id),EducationDecision,str(decision_id));read_audit(db,actor,row);return decision_view(db,actor,row)


@router.post('/support-cases/{case_id}/decisions/{decision_id}/revisions',status_code=201)
def revise_decision(school_id:UUID,case_id:UUID,decision_id:UUID,command:DecisionUpdate,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.save_decision(db,actor,str(school_id),str(case_id),command,str(decision_id)));return decision_view(db,actor,row)


@router.post('/support-cases/{case_id}/decisions/{decision_id}/confirm')
def confirm_decision(school_id:UUID,case_id:UUID,decision_id:UUID,command:Reason,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.confirm_decision(db,actor,str(school_id),str(case_id),str(decision_id),command));return decision_view(db,actor,row)


@router.get('/support-cases/{case_id}/decisions/{decision_id}/history')
def decision_history(school_id:UUID,case_id:UUID,decision_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    _,row=service.child(db,actor,str(school_id),str(case_id),EducationDecision,str(decision_id))
    revisions=db.scalars(select(DecisionRevision).where(DecisionRevision.school_id == str(school_id),DecisionRevision.decision_id == row.id).order_by(DecisionRevision.revision.desc())).all()
    value={'items':[decision_view(db,actor,row,r) for r in revisions[offset:offset+limit]],'total':len(revisions)}
    read_audit(db,actor,row);return value


@router.get('/support-cases/{case_id}/comparison')
def comparison(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    case=service.case_access(db,actor,str(school_id),str(case_id))
    recommended=[assessment_view(db,actor,r) for r in db.scalars(select(ExpertAssessment).where(ExpertAssessment.school_id == str(school_id),ExpertAssessment.case_id == case.id))]
    decided=[decision_view(db,actor,r) for r in db.scalars(select(EducationDecision).where(EducationDecision.school_id == str(school_id),EducationDecision.case_id == case.id))]
    differences=[]
    for assessment in recommended:
        for rec in assessment['recommendations']:
            matches=[p for d in decided for p in d['provisions'] if p['category'] == rec['category'] and p['subject'] == rec['subject']]
            for p in matches:
                comparable=(p['effective_from'],p['effective_until'],p['counting_basis']) == (rec['effective_from'],rec['effective_until'],rec['counting_basis']) and p['amount'] is not None and rec['amount'] is not None
                difference=None
                if comparable:
                    decided_minutes=Decimal(p['amount'])*(60 if p['unit'] == 'hours' else 1)
                    recommended_minutes=Decimal(rec['amount'])*(60 if rec['unit'] == 'hours' else 1)
                    difference=str(decided_minutes-recommended_minutes)
                differences.append({'recommendation_id':rec['id'],'provision_id':p['id'],'category':p['category'],'subject':p['subject'],'recommended_amount':rec['amount'],'recommended_unit':rec['unit'],'decided_amount':p['amount'],'decided_unit':p['unit'],'comparable':comparable,'difference_minutes':difference,'issue':'quantity_difference' if comparable and Decimal(difference) != 0 else 'different_basis' if not comparable else None})
            if not matches: differences.append({'recommendation_id':rec['id'],'issue':'no_matching_decision_provision'})
    read_audit(db,actor,case)
    return {'expert_recommendations':recommended,'binding_decisions':decided,'differences':differences,'comparison_basis':['category','subject','unit','counting_basis','effective_from','effective_until'],'warning':'Different source authorities and periods must be compared separately; totals are not merged.'}


@router.get('/support-cases/{case_id}/referrals/{referral_id}/revisions')
def referral_history(school_id:UUID,case_id:UUID,referral_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    from .models import ReferralRevision
    _,row=service.child(db,actor,str(school_id),str(case_id),Referral,str(referral_id))
    revisions=db.scalars(select(ReferralRevision).where(ReferralRevision.school_id == str(school_id),ReferralRevision.referral_id == row.id).order_by(ReferralRevision.revision.desc())).all()
    value={'items':[referral_view(db,actor,row,r) for r in revisions[offset:offset+limit]],'total':len(revisions)}
    read_audit(db,actor,row);return value


@router.post('/support-cases/{case_id}/clarifications',status_code=201)
def clarification(school_id:UUID,case_id:UUID,command:ClarificationInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.create_clarification(db,actor,str(school_id),str(case_id),command));return clarification_view(db,actor,row)


@router.get('/support-cases/{case_id}/clarifications')
def clarifications(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    from .models import CaseClarification
    case=service.case_access(db,actor,str(school_id),str(case_id))
    rows=db.scalars(select(CaseClarification).where(CaseClarification.school_id == str(school_id),CaseClarification.case_id == case.id).order_by(CaseClarification.created_at.desc(),CaseClarification.id)).all()
    values=[clarification_view(db,actor,row) for row in rows[offset:offset+limit]]
    read_audit(db,actor,case)
    return {'items':values,'total':len(rows)}


@router.post('/support-cases/{case_id}/clarifications/{clarification_id}/resolve')
def resolve(school_id:UUID,case_id:UUID,clarification_id:UUID,command:ResolveClarification,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.resolve_clarification(db,actor,str(school_id),str(case_id),str(clarification_id),command));return clarification_view(db,actor,row)


@router.get('/support-cases/{case_id}/timeline')
def timeline(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    from .models import CaseClarification
    case=service.case_access(db,actor,str(school_id),str(case_id))
    items=[{'kind':'case_created','id':case.id,'occurred_at':case.created_at,'recorded_at':case.created_at}]
    for referral in db.scalars(select(Referral).where(Referral.school_id == str(school_id),Referral.case_id == case.id)):
        items.append({'kind':'referral_prepared','id':referral.id,'occurred_at':referral.created_at,'recorded_at':referral.created_at})
        for contact in db.scalars(select(ReferralContact).where(ReferralContact.school_id == str(school_id),ReferralContact.referral_id == referral.id)):
            items.append({'kind':'referral_'+contact.kind,'id':contact.id,'referral_id':referral.id,'occurred_at':contact.occurred_at,'recorded_at':contact.recorded_at,'actual_contact':contact.actual_contact})
    for assessment in db.scalars(select(ExpertAssessment).where(ExpertAssessment.school_id == str(school_id),ExpertAssessment.case_id == case.id)):
        items.append({'kind':'expert_assessment','id':assessment.id,'occurred_at':assessment.assessment_at,'recorded_at':assessment.created_at,'state':assessment.state})
    for decision in db.scalars(select(EducationDecision).where(EducationDecision.school_id == str(school_id),EducationDecision.case_id == case.id)):
        for revision in db.scalars(select(DecisionRevision).where(DecisionRevision.school_id == str(school_id),DecisionRevision.decision_id == decision.id)):
            items.append({'kind':'decision_received','id':decision.id,'revision_id':revision.id,'occurred_at':revision.issued_at,'recorded_at':revision.created_at,'state':revision.state})
    for issue in db.scalars(select(CaseClarification).where(CaseClarification.school_id == str(school_id),CaseClarification.case_id == case.id)):
        items.append({'kind':'clarification','id':issue.id,'occurred_at':issue.created_at,'recorded_at':issue.created_at,'state':issue.state,'due_at':issue.due_at})
    items.sort(key=lambda item:(item['occurred_at'],item['id']))
    read_audit(db,actor,case)
    return {'items':items[offset:offset+limit],'total':len(items)}
