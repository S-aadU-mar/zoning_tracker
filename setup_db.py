import sqlite3

conn = sqlite3.connect("zoning.db")
cursor = conn.cursor()

# Create Tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS cities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT,
    county TEXT,
    state TEXT,
    endpoint TEXT,
    last_edit_date TEXT,
    status TEXT DEFAULT 'ACTIVE'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

# Default Employee Logins (Change these passwords!)
cursor.executemany("""
INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)
""", [
    ("admin_boss", "Pass123!", "admin"),
    ("analyst_emp", "Work2026!", "analyst"),
    ("viewer_guest", "ViewOnly1!", "viewer")
])

conn.commit()
conn.close()
print("Database ready!")
