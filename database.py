import hashlib
import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("zoning.db")

STATE_NAMES = {
    "al": "Alabama",
    "ak": "Alaska",
    "az": "Arizona",
    "ar": "Arkansas",
    "ca": "California",
    "co": "Colorado",
    "ct": "Connecticut",
    "de": "Delaware",
    "fl": "Florida",
    "ga": "Georgia",
    "hi": "Hawaii",
    "id": "Idaho",
    "il": "Illinois",
    "in": "Indiana",
    "ia": "Iowa",
    "ks": "Kansas",
    "ky": "Kentucky",
    "la": "Louisiana",
    "me": "Maine",
    "md": "Maryland",
    "ma": "Massachusetts",
    "mi": "Michigan",
    "mn": "Minnesota",
    "ms": "Mississippi",
    "mo": "Missouri",
    "mt": "Montana",
    "ne": "Nebraska",
    "nv": "Nevada",
    "nh": "New Hampshire",
    "nj": "New Jersey",
    "nm": "New Mexico",
    "ny": "New York",
    "nc": "North Carolina",
    "nd": "North Dakota",
    "oh": "Ohio",
    "ok": "Oklahoma",
    "or": "Oregon",
    "pa": "Pennsylvania",
    "ri": "Rhode Island",
    "sc": "South Carolina",
    "sd": "South Dakota",
    "tn": "Tennessee",
    "tx": "Texas",
    "ut": "Utah",
    "vt": "Vermont",
    "va": "Virginia",
    "wa": "Washington",
    "wv": "West Virginia",
    "wi": "Wisconsin",
    "wy": "Wyoming",
}
_STATE_NAMES_BY_KEY = {name.casefold(): name for name in STATE_NAMES.values()}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_state(state: str) -> str:
    value = state.strip().casefold()
    if value in STATE_NAMES:
        return STATE_NAMES[value]
    if value in _STATE_NAMES_BY_KEY:
        return _STATE_NAMES_BY_KEY[value]
    raise ValueError(f"Unknown state '{state}'. Use a full US state name or abbreviation.")


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

        for row in connection.execute("SELECT id, state FROM cities").fetchall():
            try:
                normalized_state = normalize_state(row["state"])
            except ValueError:
                continue
            if normalized_state != row["state"]:
                connection.execute(
                    "UPDATE cities SET state = ? WHERE id = ?",
                    (normalized_state, row["id"]),
                )

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
