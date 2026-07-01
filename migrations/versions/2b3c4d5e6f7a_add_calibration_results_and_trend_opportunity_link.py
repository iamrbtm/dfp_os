"""add calibration results table and trend_opportunity_id to print_jobs

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-30 22:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trend_calibration_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("trigger", sa.String(40), nullable=False, default="manual"),
        sa.Column("report_count", sa.Integer(), default=0),
        sa.Column("score_count", sa.Integer(), default=0),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("rmse", sa.Float(), nullable=True),
        sa.Column("precision_at_high_score", sa.Float(), nullable=True),
        sa.Column("recall_of_sellers", sa.Float(), nullable=True),
        sa.Column("f1_score", sa.Float(), nullable=True),
        sa.Column("zero_seller_rate", sa.Float(), nullable=True),
        sa.Column("avg_predicted_score", sa.Float(), nullable=True),
        sa.Column("total_units_sold", sa.Integer(), default=0),
        sa.Column("component_analysis", sa.JSON(), nullable=True),
        sa.Column("top_k_analysis", sa.JSON(), nullable=True),
        sa.Column("action_analysis", sa.JSON(), nullable=True),
        sa.Column("tuning_hints", sa.JSON(), nullable=True),
        sa.Column("current_weights", sa.JSON(), nullable=True),
        sa.Column("predictions_sample", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("print_jobs") as batch_op:
        batch_op.add_column(sa.Column("trend_opportunity_id", sa.Integer(), nullable=True, index=True))


def downgrade():
    with op.batch_alter_table("print_jobs") as batch_op:
        batch_op.drop_column("trend_opportunity_id")
    op.drop_table("trend_calibration_results")
