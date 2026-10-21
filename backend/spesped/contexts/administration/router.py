from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from spesped.auth import Actor,get_actor,require_authority,require_learner_access
from spesped.db import get_db
from . import schemas as s,service as svc,models as m,native as n
router=APIRouter(prefix='/api/v1/schools/{school_id}/professional-authority',tags=['professional-authority'])
def professional_db(request:Request,db:Session=Depends(get_db)):
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    db.info['curriculum_source_port']=getattr(request.app.state,'curriculum_source_port',None) or EvidenceSourceReadPort(getattr(request.app.state,'evidence_storage',None))
    for name in ('assessment_authority_port','teaching_qualification_port'):
        db.info[name]=getattr(request.app.state,name,None)
    db.info['plans_runtime']=getattr(request.app.state,'ai_gateway',None)
    db.info['teaching_runtime']=getattr(request.app.state,'ai_gateway',None)
    return db
D=Depends(professional_db);A=Depends(get_actor)
@router.post('/records',status_code=201)
def create(school_id:UUID,command:s.Create,db:Session=D,actor:Actor=A):return svc.write(db,actor,str(school_id),'create',command)
@router.post('/records/{identifier}/revisions')
def revise(school_id:UUID,identifier:UUID,command:s.Revise,db:Session=D,actor:Actor=A):return svc.write(db,actor,str(school_id),'revise',command,str(identifier))
@router.post('/records/{identifier}/review')
def review(school_id:UUID,identifier:UUID,command:s.Review,db:Session=D,actor:Actor=A):return svc.write(db,actor,str(school_id),'review',command,str(identifier))
@router.post('/records/{identifier}/revoke')
def revoke(school_id:UUID,identifier:UUID,command:s.Revoke,db:Session=D,actor:Actor=A):return svc.write(db,actor,str(school_id),'revoke',command,str(identifier))
@router.get('/records/{identifier}')
def detail(school_id:UUID,identifier:UUID,private:bool=False,db:Session=D,actor:Actor=A):
    with n.reader(db) as fresh:return svc.view(fresh,actor,str(school_id),str(identifier),private=private)
@router.get('/records')
def collection(school_id:UUID,learner_id:UUID|None=None,person_id:UUID|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id)
    with n.reader(db) as fresh:
        if learner_id:require_learner_access(fresh,actor,school_id,str(learner_id),'professional.read')
        else:require_authority(fresh,actor,school_id,'professional.read')
        filters=[m.ProfessionalRecord.school_id==school_id]
        # School-wide personnel metadata must not accidentally enumerate pupils.
        filters.append(m.ProfessionalRecord.learner_id==str(learner_id) if learner_id else m.ProfessionalRecord.learner_id.is_(None))
        if person_id:filters.append(m.ProfessionalRecord.person_id==str(person_id))
        rows=fresh.scalars(select(m.ProfessionalRecord).where(*filters).order_by(m.ProfessionalRecord.created_at,m.ProfessionalRecord.id).offset(offset).limit(limit)).all()
        total=fresh.scalar(select(func.count()).select_from(m.ProfessionalRecord).where(*filters))
        return {'items':[svc.view(fresh,actor,school_id,r.id) for r in rows],'total':total}
@router.get('/records/{identifier}/history')
def history(school_id:UUID,identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id)
    with n.reader(db) as fresh:
        row=svc.get(fresh,school_id,str(identifier));svc.view(fresh,actor,school_id,row.id)
        revisions=fresh.scalars(select(m.ProfessionalRevision).where(m.ProfessionalRevision.school_id==school_id,m.ProfessionalRevision.record_id==row.id).order_by(m.ProfessionalRevision.number).offset(offset).limit(limit)).all()
        values=[]
        for rev in revisions:
            check=svc.check(fresh,rev)
            values.append({'id':rev.id,'revision':rev.number,'digest':rev.digest,'authored_by':rev.authored_by,'authored_at':rev.created_at,'review':{'id':check.id,'reviewed_by':check.reviewer_id,'reviewed_at':check.created_at,'outcome':check.outcome} if check else None,'historical':rev.number!=row.current_revision})
        return n.encode({'items':values,'total':row.current_revision})
