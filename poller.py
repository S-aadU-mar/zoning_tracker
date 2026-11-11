import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Lock, Thread

import requests

from database import connect, initialize_database


class ScanRun:
    def __init__(self) -> None:
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.results: list[tuple[str, str]] = []
        self.total = 0
        self.state = "running"
        self.error: Exception | None = None
        self._lock = Lock()

    def request_stop(self) -> None:
        self.stop_event.set()

    def record_result(self, result: tuple[str, str]) -> None:
        with self._lock:
            self.results.append(result)

    def snapshot(self) -> tuple[str, int, int, Exception | None]:
        with self._lock:
            return self.state, len(self.results), self.total, self.error


_active_run: ScanRun | None = None
_active_run_lock = Lock()


def scan_endpoint(endpoint: str) -> tuple[str, str | None, str | None]:
    try:
        response = requests.get(endpoint, timeout=30)
        response.raise_for_status()
        content_hash = hashlib.sha256(response.content).hexdigest()
        last_modified = response.headers.get("Last-Modified")
        return "ACTIVE", last_modified, content_hash
    except requests.RequestException as error:
        return "ERROR", None, str(error)


def scan_all_endpoints(
    stop_event: Event | None = None,
    on_result: Callable[[tuple[str, str]], None] | None = None,
) -> list[tuple[str, str]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    with connect() as connection:
        cities = connection.execute("SELECT id, endpoint FROM cities").fetchall()
        if stop_event is not None and stop_event.is_set():
            return results
        for city in cities:
            if stop_event is not None and stop_event.is_set():
                break
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
            scan_result = (city["endpoint"], status)
            results.append(scan_result)
            if on_result is not None:
                on_result(scan_result)
    return results


def start_scan_run() -> ScanRun:
    global _active_run
    with _active_run_lock:
        if _active_run is not None:
            state, _, _, _ = _active_run.snapshot()
            if state == "running":
                return _active_run

        run = ScanRun()

        def execute() -> None:
            try:
                with connect() as connection:
                    run.total = connection.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
                scan_all_endpoints(run.stop_event, run.record_result)
                with run._lock:
                    run.state = "cancelled" if run.stop_event.is_set() else "completed"
            except Exception as error:
                with run._lock:
                    run.error = error
                    run.state = "failed"

        run.thread = Thread(target=execute, name="zoning-validation", daemon=True)
        _active_run = run
        run.thread.start()
        return run


def get_active_scan_run() -> ScanRun | None:
    with _active_run_lock:
        return _active_run


def main() -> None:
    initialize_database()
    for endpoint, status in scan_all_endpoints():
        print(f"{endpoint}: {status}")


if __name__ == "__main__":
    main()
