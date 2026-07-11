"""create rag ask and decision log tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_document_type", "knowledge_documents", ["document_type"])
    op.create_index("ix_knowledge_documents_source", "knowledge_documents", ["source"])
    op.create_index("ix_knowledge_documents_source_ref", "knowledge_documents", ["source_ref"])
    op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_set", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_document_index"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])

    op.create_table(
        "ask_dfp_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("decision_type", sa.String(length=80), nullable=False),
        sa.Column("user_action", sa.String(length=80), nullable=False),
        sa.Column("outcome_status", sa.String(length=80), nullable=False),
        sa.Column("actual_units", sa.Integer(), nullable=True),
        sa.Column("actual_revenue_cents", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_outcomes_decision_type", "decision_outcomes", ["decision_type"])
    op.create_index("ix_decision_outcomes_outcome_status", "decision_outcomes", ["outcome_status"])
    op.create_index("ix_decision_outcomes_recommendation_id", "decision_outcomes", ["recommendation_id"])
    op.create_index("ix_decision_outcomes_run_id", "decision_outcomes", ["run_id"])
    op.create_index("ix_decision_outcomes_user_action", "decision_outcomes", ["user_action"])


def downgrade() -> None:
    op.drop_table("decision_outcomes")
    op.drop_table("ask_dfp_runs")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
