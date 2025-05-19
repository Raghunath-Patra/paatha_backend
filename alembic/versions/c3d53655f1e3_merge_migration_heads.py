"""Merge migration heads

Revision ID: c3d53655f1e3
Revises: 8e5f77bdfe15, fa36f1a727c3
Create Date: 2025-01-12 21:08:14.151742

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d53655f1e3'
down_revision: Union[str, None] = ('8e5f77bdfe15', 'fa36f1a727c3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('questions',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=uuid.uuid4),
        sa.Column('human_readable_id', sa.String(), unique=True, nullable=False),
        sa.Column('file_source', sa.String(), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=True),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('difficulty', sa.String(), nullable=True),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('correct_answer', sa.Text(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('topic', sa.String(), nullable=True),
        sa.Column('bloom_level', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )

def downgrade() -> None:
    op.drop_table('questions')