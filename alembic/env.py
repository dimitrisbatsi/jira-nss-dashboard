import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from dotenv import load_dotenv

# 1. Βάζουμε το root folder του project στο path για να βρίσκει το φάκελο src
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')

# 2. Φορτώνουμε τα environment variables
load_dotenv()

# 3. Κάνουμε import το Base μας και το engine που έχεις ήδη φτιάξει!
from src.models.db_models import Base
from src.database.connection import engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Λέμε στο Alembic να διαβάζει τα δικά μας μοντέλα
target_metadata = Base.metadata

# 5. Περνάμε το πραγματικό connection string από το engine στο Alembic!
config.set_main_option("sqlalchemy.url", str(engine.url).replace('%', '%%'))

# --- Από εδώ και κάτω είναι οι default συναρτήσεις του Alembic ---

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def include_name(name, type_, parent_names):
    if type_ == "table":
        # Η λίστα με τους πίνακες που θέλουμε να αγνοεί το Alembic
        ignored_tables = [
            'GIsSeverity', 'GIsSN(OLD)', 'SyncAPILogin', 'User_Departments',
            'GIsPriority', 'GTimeTypes(OLD)', 'GFlexCustomer(OLD)',
            'GCustomerLSP(OLD)', 'GIsTypes', 'GIsStatus', 'GPartner(OLD)',
            'User_Email_Aliases', 'GIsPylonPack(OLD)', 'GIsCustomer(OLD)',
            'GIsResolution'
        ]
        return name not in ignored_tables
    return True

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # connectable = engine_from_config(
    #     config.get_section(config.config_ini_section, {}),
    #     prefix="sqlalchemy.",
    #     poolclass=pool.NullPool,
    # )

    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            # Εδώ προσθέτουμε μια ρύθμιση για να εντοπίζει αλλαγές σε τύπους πεδίων (όπως το UserID που έγινε String)
            compare_type=True,
            include_name=include_name
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()