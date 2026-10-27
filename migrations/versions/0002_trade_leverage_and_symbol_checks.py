"""Trades: leverage only on ETFs, symbols stored uppercase.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27

Hand-written: autogenerate doesn't detect CHECK constraints. See ADR 0007.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The naming convention turns these into ck_trades_leverage_only_etf and
    # ck_trades_symbol_uppercase.
    op.create_check_constraint(
        "leverage_only_etf", "trades", "leverage_factor IS NULL OR asset_type = 'etf'"
    )
    op.create_check_constraint("symbol_uppercase", "trades", "symbol = upper(symbol)")


def downgrade() -> None:
    op.drop_constraint("symbol_uppercase", "trades", type_="check")
    op.drop_constraint("leverage_only_etf", "trades", type_="check")
