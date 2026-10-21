"""Independent manual recovery alongside withdrawn model proposals."""
from alembic import op
import sqlalchemy as sa

revision = 'j04_manual_recovery'
down_revision = 'j04_structuring'
branch_labels = None
depends_on = None

SPAN_COLUMNS = ['school_id', 'source_id', 'source_revision', 'page', 'span_start', 'span_end', 'field_name']


def _checks():
    if op.get_bind().dialect.name != 'sqlite':
        return ()
    return (
        sa.CheckConstraint('page >= 1 AND span_start >= 0 AND span_end > span_start'),
        sa.CheckConstraint("outcome IN ('pending','accepted','edited','rejected')"),
    )


def upgrade():
    existing = sa.inspect(op.get_bind()).get_unique_constraints('evidence_proposals')
    legacy = next(c for c in existing if c['column_names'] == SPAN_COLUMNS)
    # SQLite's original constraint is unnamed; name it during batch reflection.
    legacy_name = legacy['name'] or 'uq_' + '_'.join(SPAN_COLUMNS)
    with op.batch_alter_table('evidence_proposals', naming_convention={'uq': 'uq_%(column_0_N_name)s'}, table_args=_checks()) as batch:
        batch.drop_constraint(legacy_name, type_='unique')
        batch.add_column(sa.Column('recovery_of_proposal_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_proposal_manual_recovery', 'evidence_proposals', ['school_id', 'recovery_of_proposal_id'], ['school_id', 'id'])
        batch.create_check_constraint('ck_proposal_manual_recovery', 'recovery_of_proposal_id IS NULL OR generation_job_id IS NULL')
    # Both dialects enforce origin-specific uniqueness at the database boundary.
    for name, predicate in [('uq_proposals_manual_span', 'generation_job_id IS NULL'), ('uq_proposals_model_span', 'generation_job_id IS NOT NULL')]:
        op.create_index(name, 'evidence_proposals', SPAN_COLUMNS, unique=True,
                        sqlite_where=sa.text(predicate), postgresql_where=sa.text(predicate))


def downgrade():
    columns = ', '.join(SPAN_COLUMNS)
    duplicates = op.get_bind().execute(sa.text('SELECT COUNT(*) FROM (SELECT ' + columns + ' FROM evidence_proposals GROUP BY ' + columns + ' HAVING COUNT(*) > 1) AS duplicate_spans')).scalar()
    if duplicates:
        raise RuntimeError('Independent manual/model proposal history exists; retain this schema until approved disposition permits downgrade.')
    op.drop_index('uq_proposals_manual_span', table_name='evidence_proposals')
    op.drop_index('uq_proposals_model_span', table_name='evidence_proposals')
    with op.batch_alter_table('evidence_proposals', table_args=_checks()) as batch:
        batch.drop_constraint('ck_proposal_manual_recovery', type_='check')
        batch.drop_constraint('fk_proposal_manual_recovery', type_='foreignkey')
        batch.drop_column('recovery_of_proposal_id')
        batch.create_unique_constraint('uq_proposals_legacy_span', SPAN_COLUMNS)
