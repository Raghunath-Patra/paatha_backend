"""alter question_id to uuid

Revision ID: alter_question_id_uuid
Revises: be7193b373a7  # Use your last successful revision ID here
Create Date: 2024-01-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'alter_question_id_uuid'
down_revision = 'be7193b373a7'  # Make sure this matches your last successful migration
branch_labels = None
depends_on = None

def upgrade() -> None:
    # First drop the index that uses this column
    op.drop_index('idx_user_attempts_question_user', table_name='user_attempts')
    
    # Create a new UUID column
    op.add_column('user_attempts', 
                 sa.Column('question_id_new', 
                          postgresql.UUID(as_uuid=True),
                          nullable=True))
    
    # Update the new column, converting valid UUIDs
    op.execute("""
        UPDATE user_attempts 
        SET question_id_new = question_id::uuid 
        WHERE question_id IS NOT NULL 
        AND question_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    """)
    
    # Drop old column and rename new column
    op.drop_column('user_attempts', 'question_id')
    op.alter_column('user_attempts', 'question_id_new',
                   new_column_name='question_id')
    
    # Recreate the index
    op.create_index('idx_user_attempts_question_user', 'user_attempts',
                    ['question_id', 'user_id'])

def downgrade() -> None:
    # Reverse the changes if needed
    op.drop_index('idx_user_attempts_question_user', table_name='user_attempts')
    op.alter_column('user_attempts', 'question_id',
                    type_=sa.String(),
                    postgresql_using='question_id::text')
    op.create_index('idx_user_attempts_question_user', 'user_attempts',
                    ['question_id', 'user_id'])