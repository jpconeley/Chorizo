"""rename computed benchmark source to LASO

Revision ID: 3c91201c8a6d
Revises: eef2e87fa2db
Create Date: 2026-10-29 02:26:25.198658

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c91201c8a6d"
down_revision: str | Sequence[str] | None = "eef2e87fa2db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD = "ClinicalTrials.gov (Chorizo)"
NEW = "ClinicalTrials.gov (LASO)"


def upgrade() -> None:
    """The product is now LASO; relabel benchmarks computed under the old name."""
    op.execute(
        sa.text("UPDATE stage_benchmarks SET source = :new WHERE source = :old").bindparams(old=OLD, new=NEW)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text("UPDATE stage_benchmarks SET source = :old WHERE source = :new").bindparams(old=OLD, new=NEW)
    )
