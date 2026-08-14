from alembic import op

revision = "0002_weight_group_key"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_trend_weights_key", "trend_weights", type_="unique")
    op.create_unique_constraint(
        "uq_trend_weights_group_key",
        "trend_weights",
        ["group", "key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_trend_weights_group_key", "trend_weights", type_="unique")
    op.create_unique_constraint("uq_trend_weights_key", "trend_weights", ["key"])
