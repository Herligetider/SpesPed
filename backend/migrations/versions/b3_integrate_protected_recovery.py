"""Join protected workflows and explicit manual intake recovery."""

revision = "b3_integrate_protected_recovery"
down_revision = (
    "b2_integrate_intake_plans",
    "j04_manual_recovery",
    "j16_safeguarding",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
