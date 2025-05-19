"""add_user_performance_tracking

Revision ID: d0caf7350242
Revises: 6b5f1dd7a265
Create Date: 2024-12-31 22:37:27.522691
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0caf7350242'
down_revision: Union[str, None] = '6b5f1dd7a265'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to user_attempts table
    op.add_column('user_attempts', sa.Column('question_id', sa.String(), nullable=True))
    op.add_column('user_attempts', sa.Column('answer', sa.String(), nullable=True))
    op.add_column('user_attempts', sa.Column('score', sa.Float(), nullable=True))
    op.add_column('user_attempts', sa.Column('board', sa.String(), nullable=True))
    op.add_column('user_attempts', sa.Column('class_level', sa.String(), nullable=True))
    op.add_column('user_attempts', sa.Column('subject', sa.String(), nullable=True))
    op.add_column('user_attempts', sa.Column('chapter', sa.Integer(), nullable=True))

    # Create indexes for performance
    op.create_index(op.f('ix_user_attempts_board'), 'user_attempts', ['board'], unique=False)
    op.create_index(op.f('ix_user_attempts_subject'), 'user_attempts', ['subject'], unique=False)
    op.create_index(op.f('ix_user_attempts_chapter'), 'user_attempts', ['chapter'], unique=False)
    op.create_index(op.f('ix_user_attempts_question_id'), 'user_attempts', ['question_id'], unique=False)

    # Drop the unique constraint on user_id if it exists
    try:
        op.drop_constraint('user_attempts_user_id_key', 'user_attempts', type_='unique')
    except:
        pass  # Constraint might not exist


def downgrade() -> None:
    # Remove indexes
    op.drop_index(op.f('ix_user_attempts_question_id'), table_name='user_attempts')
    op.drop_index(op.f('ix_user_attempts_chapter'), table_name='user_attempts')
    op.drop_index(op.f('ix_user_attempts_subject'), table_name='user_attempts')
    op.drop_index(op.f('ix_user_attempts_board'), table_name='user_attempts')

    # Remove columns
    op.drop_column('user_attempts', 'chapter')
    op.drop_column('user_attempts', 'subject')
    op.drop_column('user_attempts', 'class_level')
    op.drop_column('user_attempts', 'board')
    op.drop_column('user_attempts', 'score')
    op.drop_column('user_attempts', 'answer')
    op.drop_column('user_attempts', 'question_id')