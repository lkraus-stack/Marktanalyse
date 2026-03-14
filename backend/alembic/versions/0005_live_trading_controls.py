"""Extend broker enum and trade flags for live controls.

Revision ID: 0005_live_trading_controls
Revises: 0004_paper_trading_tables
Create Date: 2026-03-14 08:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_live_trading_controls"
down_revision = "0004_paper_trading_tables"
branch_labels = None
depends_on = None


old_broker_enum = sa.Enum("alpaca_paper", name="brokername", native_enum=False)
new_broker_enum = sa.Enum("alpaca_paper", "kraken", name="brokername", native_enum=False)


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    trade_columns = _existing_columns("trades")
    trade_indexes = _existing_indexes("trades")

    with op.batch_alter_table("trades") as batch_op:
        batch_op.alter_column("broker", existing_type=old_broker_enum, type_=new_broker_enum, existing_nullable=False)
        if "is_live" not in trade_columns:
            batch_op.add_column(sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    with op.batch_alter_table("trades") as batch_op:
        if "ix_trades_is_live" not in trade_indexes:
            batch_op.create_index("ix_trades_is_live", ["is_live"], unique=False)

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.alter_column("broker", existing_type=old_broker_enum, type_=new_broker_enum, existing_nullable=False)


def downgrade() -> None:
    trade_columns = _existing_columns("trades")
    trade_indexes = _existing_indexes("trades")

    with op.batch_alter_table("trades") as batch_op:
        if "ix_trades_is_live" in trade_indexes:
            batch_op.drop_index("ix_trades_is_live")

    with op.batch_alter_table("trades") as batch_op:
        if "is_live" in trade_columns:
            batch_op.drop_column("is_live")
        batch_op.alter_column("broker", existing_type=new_broker_enum, type_=old_broker_enum, existing_nullable=False)

    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.alter_column("broker", existing_type=new_broker_enum, type_=old_broker_enum, existing_nullable=False)
