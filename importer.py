import re
import sqlite3
from typing import BinaryIO

import pandas as pd

from database import normalize_state


_COLUMN_ALIASES = {
    "city": {"city", "cities", "city_name"},
    "county": {"county", "counties", "county_name"},
    "state": {"state", "states", "state_name"},
    "endpoint": {
        "endpoint",
        "endpoint_link",
        "endpoint_links",
        "endpoint_url",
        "tml",
        "url",
    },
    "last_edit_date": {"last_edit_date", "new_date", "updated_date", "date"},
}


def _normalized_header(value: object) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold())).strip("_")


def _column_map(dataframe: pd.DataFrame) -> dict[str, str]:
    normalized = [
        (_normalized_header(column), column)
        for column in dataframe.columns
    ]
    missing = []
    result = {}
    for field, aliases in _COLUMN_ALIASES.items():
        match = next(
            (
                column
                for header, column in normalized
                if any(alias in header for alias in aliases)
            ),
            None,
        )
        if match is None and field != "last_edit_date":
            missing.append(field)
        elif match is not None:
            result[field] = match
    if missing:
        raise ValueError(f"Uploaded file is missing required columns: {', '.join(missing)}.")
    return result


def _cell_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def import_cities_from_upload(uploaded_file: BinaryIO, connection: sqlite3.Connection) -> tuple[int, list[str]]:
    filename = str(getattr(uploaded_file, "name", "")).casefold()
    if filename.endswith(".csv"):
        dataframe = pd.read_csv(uploaded_file)
    elif filename.endswith(".xlsx"):
        dataframe = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Unsupported file type. Upload a CSV or XLSX file.")

    columns = _column_map(dataframe)
    added = 0
    errors = []

    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=2):
        values = {field: _cell_text(row[column]) for field, column in columns.items()}
        if not any(values.get(field) for field in ("city", "county", "state", "endpoint")):
            continue
        missing = [field for field in ("city", "county", "state", "endpoint") if not values.get(field)]
        if missing:
            errors.append(f"Row {row_number}: missing {', '.join(missing)}.")
            continue
        if not values["endpoint"].startswith(("http://", "https://")):
            errors.append(f"Row {row_number}: endpoint must start with http:// or https://.")
            continue
        try:
            state = normalize_state(values["state"])
        except ValueError as error:
            errors.append(f"Row {row_number}: {error}")
            continue

        try:
            connection.execute(
                """
                INSERT INTO cities (city, county, state, endpoint, last_edit_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    values["city"],
                    values["county"],
                    state,
                    values.get("endpoint"),
                    values.get("last_edit_date") or None,
                ),
            )
        except sqlite3.IntegrityError:
            errors.append(f"Row {row_number}: endpoint is already being monitored.")
            continue
        added += 1

    return added, errors
