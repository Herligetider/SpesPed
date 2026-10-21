"""Static BC10 document, review and opt-in draft recurrence storage."""
from alembic import op
import sqlalchemy as sa
import spesped.db
revision='j11_documents'
down_revision='j19_professional_authority'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('documents_commands',
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('request_key', sa.String(length=100), nullable=False),
        sa.Column('operation', sa.String(length=100), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('target_kind', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.String(length=36), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'actor_id', 'request_key'),
    )
    op.create_index('ix_documents_commands_school_id', 'documents_commands', ['school_id'], unique=False)
    op.create_table('documents_outbox',
        sa.Column('aggregate_id', sa.String(length=36), nullable=False),
        sa.Column('aggregate_version', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('causation_id', sa.String(length=100), nullable=False),
        sa.Column('occurred_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('recorded_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('correlation_id', sa.String(length=36), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('processed_at', spesped.db.UTCDateTime(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint('schema_version >= 1', name='ck_documents_event_schema_version'),
        sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_outbox_school_id', 'documents_outbox', ['school_id'], unique=False)
    op.create_table('documents_templates',
        sa.Column('current_revision', sa.Integer(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('updated_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_templates_school_id', 'documents_templates', ['school_id'], unique=False)
    op.create_table('documents_cases',
        sa.Column('learner_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('current_revision', sa.Integer(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('updated_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint("state IN ('draft','waiting_contributions','in_review','approved','discarded')", name=None),
        sa.ForeignKeyConstraint(['owner_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_cases_learner_id', 'documents_cases', ['learner_id'], unique=False)
    op.create_index('ix_documents_cases_school_id', 'documents_cases', ['school_id'], unique=False)
    op.create_table('documents_email_schedules',
        sa.Column('learner_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('current_revision', sa.Integer(), nullable=False),
        sa.Column('next_run_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('pause_reason', sa.String(length=100), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('updated_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint("state IN ('inactive','active','paused','ended')", name=None),
        sa.ForeignKeyConstraint(['owner_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_email_schedules_school_id', 'documents_email_schedules', ['school_id'], unique=False)
    op.create_table('documents_template_revisions',
        sa.Column('template_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'template_id'], ['documents_templates.school_id', 'documents_templates.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
        sa.UniqueConstraint('template_id', 'number'),
    )
    op.create_index('ix_documents_template_revisions_school_id', 'documents_template_revisions', ['school_id'], unique=False)
    op.create_table('documents_schedule_revisions',
        sa.Column('schedule_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'schedule_id'], ['documents_email_schedules.school_id', 'documents_email_schedules.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('schedule_id', 'number'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_schedule_revisions_school_id', 'documents_schedule_revisions', ['school_id'], unique=False)
    op.create_table('documents_snapshots',
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('learner_id', sa.String(length=36), nullable=False),
        sa.Column('cutoff', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'document_id'], ['documents_cases.school_id', 'documents_cases.id']),
        sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_snapshots_school_id', 'documents_snapshots', ['school_id'], unique=False)
    op.create_table('documents_template_reviews',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['reviewer_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_template_revisions.school_id', 'documents_template_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'revision_id'),
    )
    op.create_index('ix_documents_template_reviews_school_id', 'documents_template_reviews', ['school_id'], unique=False)
    op.create_table('documents_draft_runs',
        sa.Column('schedule_revision_id', sa.String(length=36), nullable=False),
        sa.Column('learner_id', sa.String(length=36), nullable=False),
        sa.Column('period_key', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'document_id'], ['documents_cases.school_id', 'documents_cases.id']),
        sa.ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        sa.ForeignKeyConstraint(['school_id', 'schedule_revision_id'], ['documents_schedule_revisions.school_id', 'documents_schedule_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
        sa.UniqueConstraint('school_id', 'schedule_revision_id', 'learner_id', 'period_key'),
    )
    op.create_index('ix_documents_draft_runs_school_id', 'documents_draft_runs', ['school_id'], unique=False)
    op.create_table('documents_revisions',
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('snapshot_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('configuration', sa.JSON(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('lineage', sa.JSON(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'document_id'], ['documents_cases.school_id', 'documents_cases.id']),
        sa.ForeignKeyConstraint(['school_id', 'snapshot_id'], ['documents_snapshots.school_id', 'documents_snapshots.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'number'),
        sa.UniqueConstraint('school_id', 'id'),
    )
    op.create_index('ix_documents_revisions_school_id', 'documents_revisions', ['school_id'], unique=False)
    op.create_table('documents_approvals',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('approver_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('authority', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['approver_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'revision_id'),
    )
    op.create_index('ix_documents_approvals_school_id', 'documents_approvals', ['school_id'], unique=False)
    op.create_table('documents_contribution_assignments',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('section_key', sa.String(length=100), nullable=False),
        sa.Column('contributor_id', sa.String(length=36), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False),
        sa.Column('assigned_by', sa.String(length=36), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['assigned_by'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['contributor_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'revision_id', 'section_key', 'contributor_id'),
    )
    op.create_index('ix_documents_contribution_assignments_school_id', 'documents_contribution_assignments', ['school_id'], unique=False)
    op.create_table('documents_contributions',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('section_key', sa.String(length=100), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source_keys', sa.JSON(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_contributions_school_id', 'documents_contributions', ['school_id'], unique=False)
    op.create_table('documents_proposal_reviews',
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('proposal_digest', sa.String(length=64), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('selection', sa.JSON(), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['platform_generation_jobs.id']),
        sa.ForeignKeyConstraint(['reviewer_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'document_id'], ['documents_cases.school_id', 'documents_cases.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'job_id'),
    )
    op.create_index('ix_documents_proposal_reviews_school_id', 'documents_proposal_reviews', ['school_id'], unique=False)
    op.create_table('documents_review_records',
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_review_records_school_id', 'documents_review_records', ['school_id'], unique=False)
    op.create_table('documents_scheduled_generation_requests',
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('snapshot_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('release_id', sa.String(length=36), nullable=False),
        sa.Column('configuration_binding', sa.JSON(), nullable=False),
        sa.Column('logical_key', sa.String(length=120), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('reason_code', sa.String(length=100), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('updated_at', spesped.db.UTCDateTime(), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('school_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint("state IN ('pending','queued','running','succeeded','failed','blocked')", name=None),
        sa.ForeignKeyConstraint(['owner_id'], ['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id'], ['identity_schools.id']),
        sa.ForeignKeyConstraint(['school_id', 'document_id'], ['documents_cases.school_id', 'documents_cases.id']),
        sa.ForeignKeyConstraint(['school_id', 'job_id'], ['platform_generation_jobs.school_id', 'platform_generation_jobs.id']),
        sa.ForeignKeyConstraint(['school_id', 'policy_id'], ['platform_processing_policies.school_id', 'platform_processing_policies.id']),
        sa.ForeignKeyConstraint(['school_id', 'release_id'], ['platform_model_releases.school_id', 'platform_model_releases.id']),
        sa.ForeignKeyConstraint(['school_id', 'revision_id'], ['documents_revisions.school_id', 'documents_revisions.id']),
        sa.ForeignKeyConstraint(['school_id', 'run_id'], ['documents_draft_runs.school_id', 'documents_draft_runs.id']),
        sa.ForeignKeyConstraint(['school_id', 'snapshot_id'], ['documents_snapshots.school_id', 'documents_snapshots.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id', 'id'),
        sa.UniqueConstraint('school_id', 'logical_key'),
        sa.UniqueConstraint('school_id', 'run_id'),
    )
    op.create_index('ix_documents_scheduled_generation_requests_school_id', 'documents_scheduled_generation_requests', ['school_id'], unique=False)

def downgrade():
    # Check every retained row before any DDL, including receipts and outbox.
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_commands LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_outbox LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_templates LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_cases LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_email_schedules LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_template_revisions LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_schedule_revisions LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_snapshots LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_template_reviews LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_draft_runs LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_revisions LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_approvals LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_contribution_assignments LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_contributions LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_proposal_reviews LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_review_records LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    if op.get_bind().execute(sa.text('SELECT 1 FROM documents_scheduled_generation_requests LIMIT 1')).first() is not None:
        raise RuntimeError('Retained document history exists; downgrade refused.')
    op.drop_table('documents_scheduled_generation_requests')
    op.drop_table('documents_review_records')
    op.drop_table('documents_proposal_reviews')
    op.drop_table('documents_contributions')
    op.drop_table('documents_contribution_assignments')
    op.drop_table('documents_approvals')
    op.drop_table('documents_revisions')
    op.drop_table('documents_draft_runs')
    op.drop_table('documents_template_reviews')
    op.drop_table('documents_snapshots')
    op.drop_table('documents_schedule_revisions')
    op.drop_table('documents_template_revisions')
    op.drop_table('documents_email_schedules')
    op.drop_table('documents_cases')
    op.drop_table('documents_templates')
    op.drop_table('documents_outbox')
    op.drop_table('documents_commands')
