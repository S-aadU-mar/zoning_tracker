import hashlib
from datetime import datetime, timezone

import requests

from database import connect, initialize_database


def scan_endpoint(endpoint: str) -> tuple[str, str | None, str | None]:
    try:
        response = requests.get(endpoint, timeout=30)
        response.raise_for_status()
        content_hash = hashlib.sha256(response.content).hexdigest()
        last_modified = response.headers.get("Last-Modified")
        return "ACTIVE", last_modified, content_hash
    except requests.RequestException as error:
        return "ERROR", None, str(error)


def scan_all_endpoints() -> list[tuple[str, str]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    with connect() as connection:
        cities = connection.execute("SELECT id, endpoint FROM cities").fetchall()
        for city in cities:
            status, last_edit_date, result = scan_endpoint(city["endpoint"])
            if status == "ACTIVE":
                connection.execute(
                    """
                    UPDATE cities
                    SET status = ?, last_edit_date = COALESCE(?, last_edit_date),
                        last_checked_at = ?, last_content_hash = ?, last_error = NULL
                    WHERE id = ?
                    """,
                    (status, last_edit_date, checked_at, result, city["id"]),
                )
            else:
                connection.execute(
                    """
                    UPDATE cities
                    SET status = ?, last_checked_at = ?, last_error = ?
                    WHERE id = ?
                    """,
                    (status, checked_at, result, city["id"]),
                )
            results.append((city["endpoint"], status))
    return results


def main() -> None:
    initialize_database()
    for endpoint, status in scan_all_endpoints():
        print(f"{endpoint}: {status}")


if __name__ == "__main__":
    main()
