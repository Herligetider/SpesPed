"""Complete BC09 outbox envelope without discarding retained historical events.

Legacy rows did not distinguish occurrence from entry time. Version zero makes
that limitation explicit: both times retain created_at, and each retained event
ID provides a deterministic migration correlation. Version one events use the
native emitter's distinct actual/recording times and command correlation.
"""
from alembic import op
import sqlalchemy as sa
import spesped.db

revision='j10_assessment_events'
down_revision='j10_assessment'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('assessment_outbox',sa.Column('occurred_at',spesped.db.UTCDateTime(),nullable=True))
    op.add_column('assessment_outbox',sa.Column('recorded_at',spesped.db.UTCDateTime(),nullable=True))
    op.add_column('assessment_outbox',sa.Column('correlation_id',sa.String(36),nullable=True))
    op.add_column('assessment_outbox',sa.Column('schema_version',sa.Integer(),nullable=True))
    op.execute(sa.text('UPDATE assessment_outbox SET occurred_at=created_at,recorded_at=created_at,correlation_id=id,schema_version=0'))
    with op.batch_alter_table('assessment_outbox') as batch:
        batch.alter_column('occurred_at',existing_type=spesped.db.UTCDateTime(),nullable=False)
        batch.alter_column('recorded_at',existing_type=spesped.db.UTCDateTime(),nullable=False)
        batch.alter_column('correlation_id',existing_type=sa.String(36),nullable=False)
        batch.alter_column('schema_version',existing_type=sa.Integer(),nullable=False)
        batch.create_check_constraint('ck_assessment_event_schema_version','schema_version >= 0')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM assessment_outbox LIMIT 1')).first() is not None:
        raise RuntimeError('BC09 contains retained event envelopes; downgrade refused.')
    with op.batch_alter_table('assessment_outbox') as batch:
        batch.drop_constraint('ck_assessment_event_schema_version',type_='check')
        for name in ('schema_version','correlation_id','recorded_at','occurred_at'):batch.drop_column(name)
