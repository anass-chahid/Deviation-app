from urllib.parse import quote_plus, unquote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


# SQL Server connection helpers
def _split_odbc_connect(odbc_connect: str) -> dict[str, str]:
    parts = {}
    for item in unquote_plus(odbc_connect).split(";"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key.strip().lower()] = value.strip()
    return parts


def _build_odbc_url(parts: dict[str, str], database_name: str) -> str:
    values = {
        "Driver": parts.get("driver", "{ODBC Driver 18 for SQL Server}"),
        "Server": parts["server"],
        "Database": database_name,
        "Trusted_Connection": parts.get("trusted_connection", "yes"),
        "TrustServerCertificate": parts.get("trustservercertificate", "yes"),
    }

    if "uid" in parts:
        values["UID"] = parts["uid"]
    if "pwd" in parts:
        values["PWD"] = parts["pwd"]

    connection_string = ";".join(f"{key}={value}" for key, value in values.items())
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"


def _database_name_and_master_url() -> tuple[str | None, str]:
    database_url = make_url(settings.database_url)
    odbc_connect = database_url.query.get("odbc_connect")

    if odbc_connect:
        parts = _split_odbc_connect(odbc_connect)
        database_name = parts.get("database")
        return database_name, _build_odbc_url(parts, "master")

    database_name = database_url.database
    return database_name, str(database_url.set(database="master"))


# Database creation
def ensure_database_exists() -> None:
    database_name, master_url = _database_name_and_master_url()

    if not database_name:
        return

    master_engine = create_engine(master_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)

    with master_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT DB_ID(:database_name)"),
            {"database_name": database_name},
        ).scalar()

        if not exists:
            safe_database_name = database_name.replace("]", "]]")
            connection.execute(text(f"CREATE DATABASE [{safe_database_name}]"))

    master_engine.dispose()


# Startup database initialization
def init_db() -> None:
    if settings.auto_create_database:
        ensure_database_exists()
    Base.metadata.create_all(bind=engine)
    ensure_user_role_column_supports_superuser()
    ensure_user_shift_column()
    ensure_user_active_column()
    ensure_deviation_columns()
    ensure_deviation_type_category_column()
    ensure_notification_columns()
    ensure_deviation_type_kind_column_removed()
    ensure_qc_vessel_relation_removed()


# User table compatibility migrations
def ensure_user_role_column_supports_superuser() -> None:
    with engine.begin() as connection:
        users_table_exists = connection.execute(text("SELECT OBJECT_ID('users', 'U')")).scalar()
        if users_table_exists:
            connection.execute(text("ALTER TABLE users ALTER COLUMN role VARCHAR(20) NOT NULL"))


def ensure_user_shift_column() -> None:
    with engine.begin() as connection:
        users_table_exists = connection.execute(text("SELECT OBJECT_ID('users', 'U')")).scalar()
        if not users_table_exists:
            return

        shift_exists = connection.execute(text("SELECT COL_LENGTH('users', 'shift')")).scalar()
        if shift_exists is None:
            connection.execute(text("ALTER TABLE users ADD shift VARCHAR(80) NULL"))


def ensure_user_active_column() -> None:
    with engine.begin() as connection:
        users_table_exists = connection.execute(text("SELECT OBJECT_ID('users', 'U')")).scalar()
        if not users_table_exists:
            return

        active_exists = connection.execute(text("SELECT COL_LENGTH('users', 'active')")).scalar()
        if active_exists is None:
            connection.execute(text("ALTER TABLE users ADD active BIT NOT NULL CONSTRAINT DF_users_active DEFAULT 1"))


# Deviation table compatibility migrations
def ensure_deviation_columns() -> None:
    with engine.begin() as connection:
        deviations_table_exists = connection.execute(text("SELECT OBJECT_ID('deviations', 'U')")).scalar()
        if not deviations_table_exists:
            return

        status_exists = connection.execute(text("SELECT COL_LENGTH('deviations', 'status')")).scalar()
        if status_exists is None:
            connection.execute(text("ALTER TABLE deviations ADD status VARCHAR(80) NOT NULL CONSTRAINT DF_deviations_status DEFAULT 'Not Yet'"))

        description_exists = connection.execute(text("SELECT COL_LENGTH('deviations', 'description')")).scalar()
        if description_exists is None:
            connection.execute(text("ALTER TABLE deviations ADD description VARCHAR(MAX) NULL"))

        category_exists = connection.execute(text("SELECT COL_LENGTH('deviations', 'category')")).scalar()
        area_exists = connection.execute(text("SELECT COL_LENGTH('deviations', 'area')")).scalar()
        if category_exists is None and area_exists is not None:
            connection.execute(text("EXEC sp_rename 'deviations.area', 'category', 'COLUMN'"))
        elif category_exists is None:
            connection.execute(text("ALTER TABLE deviations ADD category VARCHAR(80) NOT NULL CONSTRAINT DF_deviations_category DEFAULT 'Yard'"))

        connection.execute(text("""
            UPDATE deviations
            SET category = 'Equipment'
            WHERE category = 'Equipments'
        """))

        connection.execute(text("""
            UPDATE deviations
            SET category = 'Others'
            WHERE category NOT IN ('Equipment','Flow', 'Planning', 'Yard', 'Human', 'Others')
        """))

        duration_exists = connection.execute(text("SELECT COL_LENGTH('deviations', 'duration')")).scalar()
        if duration_exists is None:
            connection.execute(text("ALTER TABLE deviations ADD duration INT NOT NULL CONSTRAINT DF_deviations_duration DEFAULT 0"))


# Notification table compatibility migrations
def ensure_notification_columns() -> None:
    with engine.begin() as connection:
        notifications_table_exists = connection.execute(text("SELECT OBJECT_ID('notifications', 'U')")).scalar()
        if not notifications_table_exists:
            return

        read_exists = connection.execute(text("SELECT COL_LENGTH('notifications', 'read')")).scalar()
        is_read_exists = connection.execute(text("SELECT COL_LENGTH('notifications', 'is_read')")).scalar()

        if read_exists is not None and is_read_exists is None:
            connection.execute(text("EXEC sp_rename 'notifications.read', 'is_read', 'COLUMN'"))
        elif read_exists is None and is_read_exists is None:
            connection.execute(text("ALTER TABLE notifications ADD is_read BIT NOT NULL CONSTRAINT DF_notifications_is_read DEFAULT 0"))

        deviation_id_nullable = connection.execute(text("""
            SELECT is_nullable
            FROM sys.columns
            WHERE object_id = OBJECT_ID('notifications') AND name = 'deviation_id'
        """)).scalar()
        if deviation_id_nullable == 0:
            connection.execute(text("ALTER TABLE notifications ALTER COLUMN deviation_id INT NULL"))


# Deviation type compatibility migrations
def ensure_deviation_type_category_column() -> None:
    with engine.begin() as connection:
        deviation_types_table_exists = connection.execute(text("SELECT OBJECT_ID('deviation_types', 'U')")).scalar()
        if not deviation_types_table_exists:
            return

        category_exists = connection.execute(text("SELECT COL_LENGTH('deviation_types', 'category')")).scalar()
        if category_exists is None:
            connection.execute(text(
                "ALTER TABLE deviation_types ADD category VARCHAR(80) NOT NULL "
                "CONSTRAINT DF_deviation_types_category DEFAULT 'Yard'"
            ))

        connection.execute(text("""
            UPDATE deviation_types
            SET category = 'Equipment'
            WHERE category = 'Equipments'
        """))

        connection.execute(text("""
            UPDATE deviation_types
            SET category = 'Yard'
            WHERE category IS NULL
               OR category NOT IN ('Equipment','Flow', 'Planning', 'Yard', 'Human', 'Others')
        """))
