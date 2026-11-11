import hashlib
import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("zoning.db")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT NOT NULL,
                county TEXT NOT NULL,
                state TEXT NOT NULL,
                endpoint TEXT NOT NULL UNIQUE,
                last_edit_date TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                last_checked_at TEXT,
                last_content_hash TEXT,
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'analyst', 'viewer'))
            );
            """
        )

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cities)").fetchall()
        }
        for column, definition in (
            ("last_checked_at", "TEXT"),
            ("last_content_hash", "TEXT"),
            ("last_error", "TEXT"),
        ):
            if column not in columns:
                connection.execute(f"ALTER TABLE cities ADD COLUMN {column} {definition}")

        users = (
            ("admin_boss", hash_password("Pass123!"), "admin"),
            ("analyst_emp", hash_password("Work2026!"), "analyst"),
            ("viewer_guest", hash_password("ViewOnly1!"), "viewer"),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
            users,
        )


def authenticate(username: str, password: str) -> str | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT role, password FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if row and row["password"] == hash_password(password):
        return row["role"]
    return None
