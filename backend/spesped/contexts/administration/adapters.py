"""Production read-only adapters. Viewer authority and person eligibility differ."""
from sqlalchemy import select
from spesped.auth import require_learner_access
from spesped.errors import DomainError
from spesped.contexts.teaching.ports import QualificationResult,QualificationSource
from spesped.contexts.assessment.ports import AuthorityResult,AuthoritySource
from . import models as m,service as svc,native as n

def candidates(db,request,kind):
    person_id=str(request.staff_id if kind=='teaching_review' else request.person_id)
    return list(db.scalars(select(m.ProfessionalRecord).where(m.ProfessionalRecord.school_id==str(request.school_id),m.ProfessionalRecord.learner_id==str(request.learner_id),m.ProfessionalRecord.person_id==person_id,m.ProfessionalRecord.kind==kind,m.ProfessionalRecord.state!='revoked')))

def resolve(db,actor,request,kind):
    school_id=str(request.school_id);learner_id=str(request.learner_id)
    require_learner_access(db,actor,school_id,learner_id,'teaching.read' if kind=='teaching_review' else 'assessment.read')
    # Validate native target before considering any supplied professional claim.
    if kind=='teaching_review':n.teaching_target(db,actor,request)
    else:n.assessment_target(db,actor,request)
    exact=[]
    for row in candidates(db,request,kind):
        rev=svc.revision(db,row);content=svc.content_of(rev)
        if content.request!=request:continue
        exact.append((row,rev,content,svc.check(db,rev)))
    if not exact:return None,'unresolved'
    # A second active exact determination needs explicit reconciliation. No
    # convenient latest-row or positive-review-wins choice may mask conflict.
    if len(exact)!=1:return None,'unresolved'
    row,rev,content,review=exact[0]
    if review and review.outcome=='ineligible':return None,'ineligible'
    try:
        svc.current(db,row);svc.validate(db,actor,school_id,content,reviewing=True)
        refs=[content.qualification,content.responsibility]
        if kind=='assessment_review' and content.policy:refs.append(content.policy)
        sources=[{'record_id':row.id,'revision':rev.number,'digest':rev.digest}]
        for ref in refs:sources.append({'record_id':str(ref.record_id),'revision':ref.revision,'digest':ref.digest})
        return (row,rev,content,review,sources),'reviewed_current'
    except DomainError as exc:
        if exc.status_code not in {403,409}:raise
        return None,'unresolved'

class NativeQualificationReadPort:
    def resolve(self,db,actor,request):
        with n.reader(db) as fresh:
            try:value,state=resolve(fresh,actor,request,'teaching_review')
            except DomainError as exc:
                if exc.status_code==403:raise
                if exc.status_code!=409:raise
                return QualificationResult(request=request,state='unresolved')
            if value is None:return QualificationResult(request=request,state=state)
            row,rev,content,review,sources=value
            kinds=['competence_review','staff_qualification','staff_responsibility']
            return QualificationResult(request=request,state=state,responsibility='responsible_teaching',review_id=review.id,reviewed_by=review.reviewer_id,reviewed_at=review.created_at,effective_from=content.effective_from,effective_until=content.effective_until,sources=[QualificationSource(kind=k,source_id=r['record_id'],revision=r['revision'],digest=r['digest']) for k,r in zip(kinds,sources,strict=True)])

class NativeAssessmentAuthorityPort:
    def resolve(self,db,actor,request):
        with n.reader(db) as fresh:
            try:value,state=resolve(fresh,actor,request,'assessment_review')
            except DomainError as exc:
                if exc.status_code==403:raise
                if exc.status_code!=409:raise
                return AuthorityResult(request=request,state='unresolved')
            if value is None:return AuthorityResult(request=request,state=state)
            row,rev,content,review,sources=value
            policy={}
            if content.policy:
                _,_,p,_=svc.referenced(fresh,str(request.school_id),content.policy,'assessment_policy')
                policy={k:getattr(p,k) for k in ('completion','exemption','grade_policy','grade_values')}
            # validate() proved the complete school-local requested date range,
            # including first-real-instant boundaries on timezone transitions.
            return AuthorityResult(request=request,state=state,review_id=review.id,reviewed_by=review.reviewer_id,reviewed_at=review.created_at,effective_from=request.starts_on,effective_until=request.ends_on,sources=[AuthoritySource(**s) for s in sources],**policy)
