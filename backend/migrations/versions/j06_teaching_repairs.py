"""Freeze follow-up lineage, distinguish unassessed support and retain input reviews.

Legacy follow-up lineage is unknown and remains null: reconstructing it from a
newer current session would recreate the disclosure defect. Existing ITO rows
have no reviewed qualification basis and must remain unassessed until corrected.
"""
from alembic import op
import sqlalchemy as sa
import json
import spesped.db

revision='j06_teaching_repairs'
down_revision='j06_teaching'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    old_columns=['school_id','learner_id','target_type','target_id','reason_code']
    constraints=sa.inspect(bind).get_unique_constraints('teaching_follow_ups')
    old=next(c for c in constraints if c['column_names'] == old_columns)
    convention={'uq':'uq_%(table_name)s_%(column_0_N_name)s','ck':'ck_%(table_name)s_state'}
    old_name=old['name'] or 'uq_teaching_follow_ups_school_id_learner_id_target_type_target_id_reason_code'
    with op.batch_alter_table('teaching_follow_ups',naming_convention=convention) as batch:
        batch.add_column(sa.Column('dependency_binding',sa.JSON(),nullable=True))
        batch.add_column(sa.Column('dependency_key',sa.String(64),nullable=True))
        batch.drop_constraint(old_name,type_='unique')
        batch.create_unique_constraint('uq_teaching_follow_up_dependency',old_columns+['dependency_key'])
    op.execute(sa.text("UPDATE teaching_follow_ups SET dependency_key = 'legacy:' || id"))
    with op.batch_alter_table('teaching_follow_ups') as batch:batch.alter_column('dependency_key',existing_type=sa.String(64),nullable=False)
    with op.batch_alter_table('teaching_learner_participation') as batch:
        batch.add_column(sa.Column('support_status',sa.String(20),nullable=False,server_default='unassessed'))
        batch.add_column(sa.Column('qualification_binding',sa.JSON(),nullable=True))
    op.execute(sa.text("UPDATE teaching_learner_participation SET support_status = 'assessed' WHERE category != 'individually_adapted_education' AND NOT (status = 'absent' AND attributed_staff_minutes > 0)"))
    with op.batch_alter_table('teaching_learner_participation',naming_convention={'ck':'ck_%(table_name)s_nonnegative_minutes'}) as batch:batch.alter_column('support_status',existing_type=sa.String(20),server_default=None)
    with op.batch_alter_table('teaching_assistant_actual_inputs',naming_convention={'ck':'ck_%(table_name)s_state'}) as batch:
        batch.add_column(sa.Column('invalidated_by_revision_id',sa.String(36),nullable=True))
        batch.create_foreign_key('fk_teaching_input_invalidation','teaching_delivery_revisions',['school_id','invalidated_by_revision_id'],['school_id','id'])
    op.create_table('teaching_actual_input_reviews',
        sa.Column('input_id',sa.String(36),nullable=False),
        sa.Column('outcome',sa.String(30),nullable=False),
        sa.Column('delivery_revision_id',sa.String(36),nullable=True),
        sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('reviewed_by',sa.String(36),nullable=False),
        sa.Column('reviewed_at',spesped.db.UTCDateTime(),nullable=True),
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',spesped.db.UTCDateTime(),nullable=False),
        sa.Column('school_id',sa.String(36),sa.ForeignKey('identity_schools.id'),nullable=False),
        sa.ForeignKeyConstraint(['reviewed_by'],['identity_users.id']),
        sa.ForeignKeyConstraint(['school_id','input_id'],['teaching_assistant_actual_inputs.school_id','teaching_assistant_actual_inputs.id']),
        sa.ForeignKeyConstraint(['school_id','delivery_revision_id'],['teaching_delivery_revisions.school_id','teaching_delivery_revisions.id']))
    op.create_index('ix_teaching_actual_input_reviews_school_id','teaching_actual_input_reviews',['school_id'])
    # The old system retained the latest review but no review timestamp. Preserve
    # exactly what is known and leave reviewed_at unknown.
    op.execute(sa.text("INSERT INTO teaching_actual_input_reviews (id,school_id,input_id,outcome,delivery_revision_id,reason,reviewed_by,created_at,reviewed_at) SELECT id,school_id,id,state,delivery_revision_id,review_reason,reviewed_by,CURRENT_TIMESTAMP,NULL FROM teaching_assistant_actual_inputs WHERE reviewed_by IS NOT NULL AND review_reason IS NOT NULL"))

    op.execute(sa.text("UPDATE teaching_assistant_actual_inputs SET state = 'needs_clarification', invalidated_by_revision_id = (SELECT current_rev.id FROM teaching_delivery_revisions AS old_rev JOIN teaching_deliveries AS actual ON actual.id = old_rev.delivery_id AND actual.school_id = old_rev.school_id JOIN teaching_delivery_revisions AS current_rev ON current_rev.delivery_id = actual.id AND current_rev.school_id = actual.school_id AND current_rev.revision = actual.current_revision WHERE old_rev.id = teaching_assistant_actual_inputs.delivery_revision_id AND old_rev.school_id = teaching_assistant_actual_inputs.school_id) WHERE state = 'recorded' AND EXISTS (SELECT 1 FROM teaching_delivery_revisions AS old_rev JOIN teaching_deliveries AS actual ON actual.id = old_rev.delivery_id AND actual.school_id = old_rev.school_id WHERE old_rev.id = teaching_assistant_actual_inputs.delivery_revision_id AND old_rev.school_id = teaching_assistant_actual_inputs.school_id AND (actual.current_revision != old_rev.revision OR actual.state = 'cancelled'))"))

def downgrade():
    # Downgrade is safe only when its old unique key is still representable.
    # Refuse rather than discard distinct historical impacts created since upgrade.
    duplicate=op.get_bind().execute(sa.text('SELECT 1 FROM teaching_follow_ups GROUP BY school_id,learner_id,target_type,target_id,reason_code HAVING COUNT(*) > 1')).first()
    if duplicate:raise RuntimeError('Distinct frozen follow-up histories cannot be represented by the old schema')
    bind=op.get_bind()
    def has_binding(query):
        for row in bind.execute(sa.text(query)):
            value=json.loads(row[0]) if isinstance(row[0],str) else row[0]
            if value is not None:return True
        return False
    frozen=has_binding('SELECT dependency_binding FROM teaching_follow_ups')
    qualified=has_binding('SELECT qualification_binding FROM teaching_learner_participation')
    reviewed=bind.execute(sa.text('SELECT 1 FROM teaching_actual_input_reviews WHERE reviewed_at IS NOT NULL')).first()
    invalidated=bind.execute(sa.text('SELECT 1 FROM teaching_assistant_actual_inputs WHERE invalidated_by_revision_id IS NOT NULL')).first()
    if frozen or qualified or reviewed or invalidated:raise RuntimeError('Frozen teaching dependencies, qualifications, review history and reconciliation recovery cannot be discarded by a downgrade')
    op.drop_index('ix_teaching_actual_input_reviews_school_id',table_name='teaching_actual_input_reviews')
    op.drop_table('teaching_actual_input_reviews')
    with op.batch_alter_table('teaching_assistant_actual_inputs',naming_convention={'ck':'ck_%(table_name)s_state'}) as batch:
        batch.drop_constraint('fk_teaching_input_invalidation',type_='foreignkey')
        batch.drop_column('invalidated_by_revision_id')
    with op.batch_alter_table('teaching_learner_participation') as batch:
        batch.drop_column('qualification_binding');batch.drop_column('support_status')
    with op.batch_alter_table('teaching_follow_ups') as batch:
        batch.drop_constraint('uq_teaching_follow_up_dependency',type_='unique')
        batch.create_unique_constraint('uq_teaching_follow_up_legacy',['school_id','learner_id','target_type','target_id','reason_code'])
        batch.drop_column('dependency_binding');batch.drop_column('dependency_key')
