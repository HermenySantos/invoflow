from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {}
engine_kwargs: dict = {"pool_pre_ping": True}

if settings.database_url.startswith("sqlite"):
    # SQLite-specific configuration
    connect_args = {"check_same_thread": False}
    # SQLite + QueuePool + pool_size is a common local-dev crash.
    engine_kwargs = {}
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_missing_nullable_columns(bind) -> list[str]:
    """Development helper: add nullable model columns an existing local table lacks.

    create_all() skips tables that already exist, so a local demo database made
    before a new column would otherwise fail on every query. Real databases are
    migrated with Alembic instead.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(bind)
    added: list[str] = []
    with bind.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                column_type = column.type.compile(dialect=bind.dialect)
                connection.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}'))
                added.append(f"{table.name}.{column.name}")
    return added
