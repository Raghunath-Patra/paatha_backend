"""create_questions_table

Revision ID: fa36f1a727c3
Revises: fcf6e8e8613e
Create Date: 2025-01-12 20:49:09.059586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa36f1a727c3'
down_revision: Union[str, None] = 'fcf6e8e8613e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass