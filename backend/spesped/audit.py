from spesped.contexts.identity.models import AuditRecord


def record_audit(db, actor, school_id, action, target_type, target_id):
    """Add metadata only; the caller owns the transaction and commit."""
    record = AuditRecord(actor_id=actor.user_id, school_id=school_id, action=action, target_type=target_type, target_id=target_id, outcome="success")
    db.add(record)
    return record
