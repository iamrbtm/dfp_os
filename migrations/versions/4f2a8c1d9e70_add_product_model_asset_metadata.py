"""Add product model asset metadata configuration.

Revision ID: 4f2a8c1d9e70
Revises: add_business_id_to_print_jobs
"""

from alembic import op
import sqlalchemy as sa

revision = "4f2a8c1d9e70"
down_revision = "add_business_id_to_print_jobs"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("model_metadata_path", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("model_analysis_config", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "model_convert_to_glb",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("model_convert_to_glb")
        batch_op.drop_column("model_analysis_config")
        batch_op.drop_column("model_metadata_path")
