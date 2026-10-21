"""Persist professional qualification, responsibility and scoped human review.

External source references explicitly represent human verification only.
"""
from alembic import op
import sqlalchemy as sa
import spesped.db
revision='j19_professional_authority'
down_revision='j10_assessment_events'
branch_labels=None
depends_on=None

def upgrade():
    # Static schema, independent of runtime models.
    op.create_table('administration_professional_commands',
    sa.Column('actor_id', sa.String(length=36), nullable=False),
    sa.Column('request_key', sa.String(length=120), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'actor_id', 'request_key')
    )
    op.create_index(op.f('ix_administration_professional_commands_school_id'), 'administration_professional_commands', ['school_id'], unique=False)
    op.create_table('administration_professional_outbox',
    sa.Column('aggregate_id', sa.String(length=36), nullable=False),
    sa.Column('aggregate_version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('occurred_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('recorded_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('correlation_id', sa.String(length=36), nullable=False),
    sa.Column('causation_id', sa.String(length=120), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint('schema_version >= 1'),
    sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_administration_professional_outbox_school_id'), 'administration_professional_outbox', ['school_id'], unique=False)
    op.create_table('administration_professional_records',
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('learner_id', sa.String(length=36), nullable=True),
    sa.Column('person_id', sa.String(length=36), nullable=True),
    sa.Column('current_revision', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("kind IN ('qualification','responsibility','assessment_policy','teaching_review','assessment_review')"),
    sa.CheckConstraint("state IN ('draft','reviewed','revoked')"),
    sa.ForeignKeyConstraint(['person_id'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id')
    )
    op.create_index(op.f('ix_administration_professional_records_learner_id'), 'administration_professional_records', ['learner_id'], unique=False)
    op.create_index(op.f('ix_administration_professional_records_person_id'), 'administration_professional_records', ['person_id'], unique=False)
    op.create_index(op.f('ix_administration_professional_records_school_id'), 'administration_professional_records', ['school_id'], unique=False)
    op.create_table('administration_professional_revisions',
    sa.Column('record_id', sa.String(length=36), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('authored_by', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['authored_by'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id', 'record_id'], ['administration_professional_records.school_id', 'administration_professional_records.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('record_id', 'number'),
    sa.UniqueConstraint('school_id', 'id')
    )
    op.create_index(op.f('ix_administration_professional_revisions_school_id'), 'administration_professional_revisions', ['school_id'], unique=False)
    op.create_table('administration_professional_checks',
    sa.Column('revision_id', sa.String(length=36), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('reviewer_id', sa.String(length=36), nullable=False),
    sa.Column('authority_action', sa.String(length=100), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('source_checked_on', sa.Date(), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("outcome IN ('eligible','ineligible','unresolved')"),
    sa.ForeignKeyConstraint(['reviewer_id'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['administration_professional_revisions.school_id', 'administration_professional_revisions.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'revision_id')
    )
    op.create_index(op.f('ix_administration_professional_checks_school_id'), 'administration_professional_checks', ['school_id'], unique=False)
    op.create_table('administration_professional_revocations',
    sa.Column('record_id', sa.String(length=36), nullable=False),
    sa.Column('revision_id', sa.String(length=36), nullable=False),
    sa.Column('revoked_by', sa.String(length=36), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', spesped.db.UTCDateTime(timezone=True), nullable=False),
    sa.Column('school_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['revoked_by'], ['identity_users.id'], ),
    sa.ForeignKeyConstraint(['school_id', 'record_id'], ['administration_professional_records.school_id', 'administration_professional_records.id'], ),
    sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['administration_professional_revisions.school_id', 'administration_professional_revisions.id'], ),
    sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'record_id')
    )
    op.create_index(op.f('ix_administration_professional_revocations_school_id'), 'administration_professional_revocations', ['school_id'], unique=False)

def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_commands LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_outbox LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_records LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_revisions LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_checks LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM administration_professional_revocations LIMIT 1')).first() is not None:
        raise RuntimeError('Retained professional history exists; downgrade refused.')
    op.drop_table('administration_professional_revocations')
    op.drop_table('administration_professional_checks')
    op.drop_table('administration_professional_revisions')
    op.drop_table('administration_professional_records')
    op.drop_table('administration_professional_outbox')
    op.drop_table('administration_professional_commands')
