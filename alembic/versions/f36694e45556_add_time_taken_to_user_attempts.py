"""add time_taken to user attempts

Revision ID: f36694e45556
Revises: alter_question_id_uuid
Create Date: [current date]
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f36694e45556'
down_revision: Union[str, None] = 'alter_question_id_uuid'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('user_attempts', sa.Column('time_taken', sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column('user_attempts', 'time_taken')