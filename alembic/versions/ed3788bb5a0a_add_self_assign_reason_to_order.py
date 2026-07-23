"""add self_assign_reason to order

Revision ID: ed3788bb5a0a
Revises: 8f2a1c9d4b3e
Create Date: 2026-07-23 11:35:02.070572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ed3788bb5a0a'
down_revision: Union[str, Sequence[str], None] = '8f2a1c9d4b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('order', sa.Column('self_assign_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('order', 'self_assign_reason')
