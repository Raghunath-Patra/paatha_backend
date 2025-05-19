"""add_time_taken_column

Revision ID: a5fb82dc96c4
Revises: f36694e45556
Create Date: 2025-01-18 11:13:07.111896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5fb82dc96c4'
down_revision: Union[str, None] = 'f36694e45556'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add time_taken column to user_attempts table
    op.add_column('user_attempts', sa.Column('time_taken', sa.Integer(), nullable=True))

def downgrade() -> None:
    # Remove time_taken column from user_attempts table
    op.drop_column('user_attempts', 'time_taken')