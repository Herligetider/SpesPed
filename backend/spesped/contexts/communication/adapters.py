"""Fresh transaction-bound reads; historical acceptance does not grant current content access."""
from contextlib import contextmanager
from functools import wraps
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import require_learner_access
from spesped.errors import DomainError
from spesped.contexts.documents.adapters import digest,encode
from spesped.contexts.documents.ports import SentPeriod
from . import models as m
@contextmanager
def owner_reader(db):
    if any(type(r).__module__.startswith('spesped.contexts.') for r in db.new|db.dirty|db.deleted):raise DomainError('dependency_pending','Flush or roll back staged changes before reading communication.',409)
    with db.no_autoflush:
        reader=Session(bind=db.connection(),join_transaction_mode='rollback_only',autoflush=False,expire_on_commit=False);reader.info.update(db.info)
        try:yield reader
        finally:reader.close()
def read_contract(fn):
    @wraps(fn)
    def read(db,*args,**kwargs):
        with owner_reader(db) as reader:return fn(reader,*args,**kwargs)
    return read
class NativeDispatchHistoryPort:
    def confirmed_periods(self,db,actor,school_id,learner_id,recipient_relationship_id,purpose):
        with owner_reader(db) as reader:return self._confirmed(reader,actor,school_id,learner_id,recipient_relationship_id,purpose)
    def _confirmed(self,db,actor,school_id,learner_id,recipient_relationship_id,purpose):
        require_learner_access(db,actor,school_id,learner_id,'documents.read')
        rows=db.execute(select(m.Dispatch,m.PackageRevision).join(m.PackageRevision,m.Dispatch.revision_id==m.PackageRevision.id).join(m.DisclosurePackage,m.Dispatch.package_id==m.DisclosurePackage.id).where(m.Dispatch.school_id==school_id,m.DisclosurePackage.learner_id==learner_id,m.Dispatch.state=='accepted')).all();values=[]
        for dispatch,revision in rows:
            manifest=revision.manifest
            if digest(manifest)!=revision.digest:raise DomainError('package_integrity','A retained dispatch package failed integrity validation.',409)
            if manifest['relationship_id']!=recipient_relationship_id or manifest['purpose']!=purpose:continue
            if db.scalar(select(m.DeliveryReceipt.id).where(m.DeliveryReceipt.school_id==school_id,m.DeliveryReceipt.dispatch_id==dispatch.id,m.DeliveryReceipt.outcome=='accepted')) is None:continue
            values.append(SentPeriod(school_id=school_id,learner_id=learner_id,dispatch_id=dispatch.id,document_revision_id=manifest['document_revision_id'],package_digest=revision.digest,recipient_relationship_id=recipient_relationship_id,purpose=purpose,starts_on=manifest['period']['starts_on'],ends_on=manifest['period']['ends_on']))
        return values
