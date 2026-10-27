"""Trades: cancelled_at, required exactly when the trade is cancelled.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27

Hand-written: autogenerate doesn't detect CHECK constraint changes or write backfills.
See ADR 0012. The constraint SQL is copied here, not imported from the model, so this
migration keeps meaning the same thing when the model changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NO_ENTRY = "entry_price IS NULL AND entry_at IS NULL AND quantity IS NULL"
_NO_EXIT = "exit_price IS NULL AND exit_at IS NULL AND fees IS NULL AND followed_plan IS NULL"
_ENTRY = "entry_price IS NOT NULL AND entry_at IS NOT NULL AND quantity IS NOT NULL"
_EXIT = (
    "exit_price IS NOT NULL AND exit_at IS NOT NULL AND fees IS NOT NULL"
    " AND followed_plan IS NOT NULL"
)

_OLD_STATUS_FIELDS = (
    f"(status IN ('planned', 'cancelled') AND {_NO_ENTRY} AND {_NO_EXIT})"
    f" OR (status = 'open' AND {_ENTRY} AND {_NO_EXIT})"
    f" OR (status = 'closed' AND {_ENTRY} AND {_EXIT})"
)
_NEW_STATUS_FIELDS = (
    f"(status = 'planned' AND {_NO_ENTRY} AND {_NO_EXIT} AND cancelled_at IS NULL)"
    f" OR (status = 'cancelled' AND {_NO_ENTRY} AND {_NO_EXIT} AND cancelled_at IS NOT NULL)"
    f" OR (status = 'open' AND {_ENTRY} AND {_NO_EXIT} AND cancelled_at IS NULL)"
    f" OR (status = 'closed' AND {_ENTRY} AND {_EXIT} AND cancelled_at IS NULL)"
)


def upgrade() -> None:
    op.add_column("trades", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    # Rows cancelled before this column existed: updated_at is the best estimate we have.
    op.execute("UPDATE trades SET cancelled_at = updated_at WHERE status = 'cancelled'")
    op.drop_constraint("status_fields", "trades", type_="check")
    op.create_check_constraint("status_fields", "trades", _NEW_STATUS_FIELDS)
    op.create_index("ix_trades_user_id_cancelled_at", "trades", ["user_id", "cancelled_at"])


def downgrade() -> None:
    op.drop_index("ix_trades_user_id_cancelled_at", table_name="trades")
    op.drop_constraint("status_fields", "trades", type_="check")
    op.create_check_constraint("status_fields", "trades", _OLD_STATUS_FIELDS)
    op.drop_column("trades", "cancelled_at")
