"""Allow nullable sentiment fields for raw social/news ingestion.

Revision ID: 0002_social_raw_sentiment_nullable
Revises: 0001_initial_schema
Create Date: 2026-03-13 15:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_social_raw_sentiment_nullable"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Permit raw sentiment records before NLP enrichment."""
    with op.batch_alter_table("sentiment_records") as batch:
        batch.alter_column("sentiment_score", existing_type=sa.Float(), nullable=True)
        batch.alter_column(
            "sentiment_label",
            existing_type=sa.Enum("positive", "negative", "neutral", name="sentimentlabel", native_enum=False),
            nullable=True,
        )
        batch.alter_column(
            "model_used",
            existing_type=sa.Enum("finvader", "finbert", "pre_labeled", name="sentimentmodel", native_enum=False),
            nullable=True,
        )
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=True)
        batch.create_index("ix_sentiment_records_source_url", ["source_url"], unique=False)


def downgrade() -> None:
    """Restore strict non-null sentiment columns."""
    op.execute(
        sa.text(
            "UPDATE sentiment_records "
            "SET sentiment_score = 0.0, sentiment_label = 'neutral', model_used = 'pre_labeled', confidence = 0.0 "
            "WHERE sentiment_score IS NULL OR sentiment_label IS NULL OR model_used IS NULL OR confidence IS NULL"
        )
    )
    with op.batch_alter_table("sentiment_records") as batch:
        batch.drop_index("ix_sentiment_records_source_url")
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=False)
        batch.alter_column(
            "model_used",
            existing_type=sa.Enum("finvader", "finbert", "pre_labeled", name="sentimentmodel", native_enum=False),
            nullable=False,
        )
        batch.alter_column(
            "sentiment_label",
            existing_type=sa.Enum("positive", "negative", "neutral", name="sentimentlabel", native_enum=False),
            nullable=False,
        )
        batch.alter_column("sentiment_score", existing_type=sa.Float(), nullable=False)
