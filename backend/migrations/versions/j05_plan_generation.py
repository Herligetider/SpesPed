"""Immutable IEP generation basis, human selections and per-field lineage."""
from alembic import op
import sqlalchemy as sa
from spesped.db import UTCDateTime

revision='j05_plan_generation'
down_revision='j06_teaching'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('plans_revisions',sa.Column('generation_lineage',sa.JSON(),nullable=False,server_default='{}'))
    op.create_table('plans_generation_bases',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('school_id',sa.String(36),sa.ForeignKey('identity_schools.id'),nullable=False,index=True),
        sa.Column('learner_id',sa.String(36),nullable=False),
        sa.Column('plan_id',sa.String(36),nullable=False),
        sa.Column('plan_revision_id',sa.String(36),nullable=False),
        sa.Column('content',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('dependencies',sa.JSON(),nullable=False),sa.Column('dependency_digest',sa.String(64),nullable=False),
        sa.Column('created_by',sa.String(36),sa.ForeignKey('identity_users.id'),nullable=False),
        sa.Column('created_at',UTCDateTime(),nullable=False),
        sa.UniqueConstraint('school_id','id'),
        sa.ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),
        sa.ForeignKeyConstraint(['school_id','plan_id'],['plans_individual_education_plans.school_id','plans_individual_education_plans.id']),
        sa.ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']))
    op.create_table('plans_proposal_reviews',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('school_id',sa.String(36),sa.ForeignKey('identity_schools.id'),nullable=False,index=True),
        sa.Column('plan_id',sa.String(36),nullable=False),sa.Column('plan_revision_id',sa.String(36),nullable=False),
        sa.Column('basis_id',sa.String(36),nullable=False),sa.Column('job_id',sa.String(36),nullable=False),
        sa.Column('proposal_digest',sa.String(64),nullable=False),sa.Column('outcome',sa.String(20),nullable=False),
        sa.Column('selected_fields',sa.JSON(),nullable=False),sa.Column('selected_goal_keys',sa.JSON(),nullable=False),
        sa.Column('reviewer_id',sa.String(36),sa.ForeignKey('identity_users.id'),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),sa.Column('reviewed_at',UTCDateTime(),nullable=False),
        sa.ForeignKeyConstraint(['school_id','plan_id'],['plans_individual_education_plans.school_id','plans_individual_education_plans.id']),
        sa.ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']),
        sa.ForeignKeyConstraint(['school_id','basis_id'],['plans_generation_bases.school_id','plans_generation_bases.id']),
        sa.ForeignKeyConstraint(['school_id','job_id'],['platform_generation_jobs.school_id','platform_generation_jobs.id']),
        sa.CheckConstraint("outcome IN ('applied','rejected','discarded')"),sa.UniqueConstraint('school_id','job_id'))


def downgrade():
    op.drop_table('plans_proposal_reviews')
    op.drop_table('plans_generation_bases')
    # The column has no referring constraint. Native DROP COLUMN preserves
    # legacy unnamed checks that SQLite batch table recreation would omit.
    op.drop_column('plans_revisions','generation_lineage')
