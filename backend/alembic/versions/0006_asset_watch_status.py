"""Add watchlist/holding metadata to assets.

Revision ID: 0006_asset_watch_status
Revises: 0005_live_trading_controls
Create Date: 2026-03-14 09:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_asset_watch_status"
down_revision = "0005_live_trading_controls"
branch_labels = None
depends_on = None


watch_status_enum = sa.Enum("none", "watchlist", "holding", name="watchstatus", native_enum=False)


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _existing_columns("assets")
    indexes = _existing_indexes("assets")

    with op.batch_alter_table("assets") as batch_op:
        if "watch_status" not in columns:
            batch_op.add_column(
                sa.Column("watch_status", watch_status_enum, nullable=False, server_default=sa.text("'none'"))
            )
        if "watch_notes" not in columns:
            batch_op.add_column(sa.Column("watch_notes", sa.String(length=255), nullable=True))

    with op.batch_alter_table("assets") as batch_op:
        if "ix_assets_watch_status" not in indexes:
            batch_op.create_index("ix_assets_watch_status", ["watch_status"], unique=False)


def downgrade() -> None:
    columns = _existing_columns("assets")
    indexes = _existing_indexes("assets")

    with op.batch_alter_table("assets") as batch_op:
        if "ix_assets_watch_status" in indexes:
            batch_op.drop_index("ix_assets_watch_status")

    with op.batch_alter_table("assets") as batch_op:
        if "watch_notes" in columns:
            batch_op.drop_column("watch_notes")
        if "watch_status" in columns:
            batch_op.drop_column("watch_status")
