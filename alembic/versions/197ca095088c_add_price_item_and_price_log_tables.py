"""add price item and price log tables

Revision ID: 197ca095088c
Revises: 4cc9dd7701d8
Create Date: 2026-07-22 15:49:22.423624

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '197ca095088c'
down_revision: Union[str, Sequence[str], None] = '4cc9dd7701d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('priceitem',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('price_text', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pricelogentry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('item_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('old_value', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('new_value', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pricelogentry')
    op.drop_table('priceitem')
