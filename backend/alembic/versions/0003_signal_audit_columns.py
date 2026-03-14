"""Ensure trading signal audit columns exist.

Revision ID: 0003_signal_audit_columns
Revises: 0002_social_raw_sentiment_nullable
Create Date: 2026-03-14 06:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_signal_audit_columns"
down_revision = "0002_social_raw_sentiment_nullable"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _existing_columns("trading_signals")
    indexes = _existing_indexes("trading_signals")

    with op.batch_alter_table("trading_signals") as batch_op:
        if "execution_id" not in columns:
            batch_op.add_column(sa.Column("execution_id", sa.String(length=100), nullable=True))
        if "strategy_id" not in columns:
            batch_op.add_column(sa.Column("strategy_id", sa.String(length=100), nullable=True))

    with op.batch_alter_table("trading_signals") as batch_op:
        if "ix_trading_signals_execution_id" not in indexes:
            batch_op.create_index("ix_trading_signals_execution_id", ["execution_id"], unique=False)
        if "ix_trading_signals_strategy_id" not in indexes:
            batch_op.create_index("ix_trading_signals_strategy_id", ["strategy_id"], unique=False)


def downgrade() -> None:
    columns = _existing_columns("trading_signals")
    indexes = _existing_indexes("trading_signals")

    with op.batch_alter_table("trading_signals") as batch_op:
        if "ix_trading_signals_execution_id" in indexes:
            batch_op.drop_index("ix_trading_signals_execution_id")
        if "ix_trading_signals_strategy_id" in indexes:
            batch_op.drop_index("ix_trading_signals_strategy_id")

    with op.batch_alter_table("trading_signals") as batch_op:
        if "execution_id" in columns:
            batch_op.drop_column("execution_id")
        if "strategy_id" in columns:
            batch_op.drop_column("strategy_id")
