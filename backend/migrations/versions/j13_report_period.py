"""Append-only reviewed reporting intervals; legacy obligations remain unresolved."""
from alembic import op
import sqlalchemy as sa
from spesped.db import UTCDateTime

revision = 'j13_report_period'
down_revision = 'j11_documents'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('governance_report_period_reviews',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('school_id', sa.String(36), nullable=False),
        sa.Column('obligation_id', sa.String(36), nullable=False),
        sa.Column('learner_id', sa.String(36), nullable=False),
        sa.Column('document_kind', sa.String(100), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=False),
        sa.Column('obligation_basis_digest', sa.String(64), nullable=False),
        sa.Column('reviewed_binding', sa.JSON(), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=False),
        sa.Column('rationale', sa.String(2000), nullable=False),
        sa.Column('request_key', sa.String(200), nullable=False),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('recorded_at', UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id', 'obligation_id'], ['governance_obligations.school_id', 'governance_obligations.id']),
        sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        sa.UniqueConstraint('school_id', 'id'),
        sa.UniqueConstraint('school_id', 'request_key'),
        sa.UniqueConstraint('obligation_id', 'document_kind', 'revision'),
        sa.CheckConstraint('ends_on >= starts_on'),
        sa.CheckConstraint('revision >= 1'),
        sa.CheckConstraint("action IN ('review', 'revoke')"),
    )
    op.create_index('ix_governance_report_period_reviews_school_id', 'governance_report_period_reviews', ['school_id'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('''CREATE FUNCTION governance_report_period_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Reporting period review history is append-only'; END; $$''')
        op.execute('''CREATE TRIGGER governance_report_period_immutable BEFORE UPDATE OR DELETE ON governance_report_period_reviews
            FOR EACH ROW EXECUTE FUNCTION governance_report_period_append_only()''')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM governance_report_period_reviews LIMIT 1')).first() is not None:
        raise RuntimeError('Retained reporting period review history exists; downgrade refused.')
    if op.get_bind().execute(sa.text("SELECT 1 FROM governance_outbox WHERE event_type LIKE 'governance.report_period.%' LIMIT 1")).first() is not None:
        raise RuntimeError('Retained reporting period review events exist; downgrade refused.')
    op.drop_table('governance_report_period_reviews')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION governance_report_period_append_only()')
