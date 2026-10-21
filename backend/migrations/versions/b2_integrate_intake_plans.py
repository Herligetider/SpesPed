"""Join independently versioned intake and plan migrations."""

revision = "b2_integrate_intake_plans"
down_revision = ("j04_structuring", "j05_plans")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
