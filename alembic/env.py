# backend/alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from dotenv import load_dotenv

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import your models
from models import Base

# Load environment variables
load_dotenv()

# Construct database URL from Supabase environment variables
db_user = os.getenv("SUPABASE_DB_USER", "postgres")
db_password = os.getenv("SUPABASE_DB_PASSWORD", "")
db_host = os.getenv("SUPABASE_DB_HOST", "")
db_port = os.getenv("SUPABASE_DB_PORT", "5432")
db_name = os.getenv("SUPABASE_DB_NAME", "")

database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Alembic Config object
config = context.config

# Set the sqlalchemy.url value in the config
if database_url and all([db_user, db_password, db_host, db_name]):
    config.set_main_option("sqlalchemy.url", database_url)
else:
    raise ValueError("Database connection parameters are incomplete. Check your environment variables.")

# Interpret the config file for logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()