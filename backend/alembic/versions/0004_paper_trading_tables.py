"""Add paper trading tables for trades and portfolio snapshots.

Revision ID: 0004_paper_trading_tables
Revises: 0003_signal_audit_columns
Create Date: 2026-03-14 07:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_paper_trading_tables"
down_revision = "0003_signal_audit_columns"
branch_labels = None
depends_on = None


broker_enum = sa.Enum("alpaca_paper", name="brokername", native_enum=False)
trade_side_enum = sa.Enum("buy", "sell", name="tradeside", native_enum=False)
trade_status_enum = sa.Enum(
    "pending_confirmation",
    "submitted",
    "filled",
    "canceled",
    "rejected",
    "failed",
    name="tradestatus",
    native_enum=False,
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("trades"):
        op.create_table(
            "trades",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.Integer(), nullable=True),
            sa.Column("broker", broker_enum, nullable=False),
            sa.Column("order_id", sa.String(length=120), nullable=True),
            sa.Column("side", trade_side_enum, nullable=False),
            sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("total_value", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("status", trade_status_enum, nullable=False),
            sa.Column("signal_id", sa.Integer(), nullable=True),
            sa.Column("is_paper", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["signal_id"], ["trading_signals.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_trades_asset_id", "trades", ["asset_id"], unique=False)
        op.create_index("ix_trades_broker", "trades", ["broker"], unique=False)
        op.create_index("ix_trades_order_id", "trades", ["order_id"], unique=False)
        op.create_index("ix_trades_side", "trades", ["side"], unique=False)
        op.create_index("ix_trades_status", "trades", ["status"], unique=False)
        op.create_index("ix_trades_signal_id", "trades", ["signal_id"], unique=False)
        op.create_index("ix_trades_is_paper", "trades", ["is_paper"], unique=False)
        op.create_index("ix_trades_created_at", "trades", ["created_at"], unique=False)
        op.create_index("ix_trades_filled_at", "trades", ["filled_at"], unique=False)

    if not _table_exists("portfolio_snapshots"):
        op.create_table(
            "portfolio_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("broker", broker_enum, nullable=False),
            sa.Column("total_value", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("cash", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("positions_value", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("daily_pnl", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("total_pnl", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_portfolio_snapshots_broker", "portfolio_snapshots", ["broker"], unique=False)
        op.create_index("ix_portfolio_snapshots_snapshot_at", "portfolio_snapshots", ["snapshot_at"], unique=False)


def downgrade() -> None:
    if _table_exists("portfolio_snapshots"):
        op.drop_table("portfolio_snapshots")
    if _table_exists("trades"):
        op.drop_table("trades")
