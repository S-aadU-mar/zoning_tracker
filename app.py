import sqlite3

import pandas as pd
import streamlit as st

from database import authenticate, connect, initialize_database, normalize_state
from functions import main as validate_data, validate_input_columns
from importer import import_cities_from_upload
from poller import scan_all_endpoints


st.set_page_config(page_title="Zoning Tracker", page_icon="🏙️", layout="wide")
initialize_database()


def load_cities() -> pd.DataFrame:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT city, county, state, endpoint, last_edit_date, status,
                   last_checked_at, last_error
            FROM cities
            ORDER BY state, city
            """
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


st.sidebar.title("Employee Portal Login")
if "role" not in st.session_state:
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login", type="primary"):
        role = authenticate(username, password)
        if role:
            st.session_state["role"] = role
            st.rerun()
        st.sidebar.error("Invalid username or password")
else:
    st.sidebar.success(f"Logged in as {st.session_state['role'].upper()}")
    if st.sidebar.button("Log out"):
        del st.session_state["role"]
        st.rerun()

if "role" not in st.session_state:
    st.info("Please enter your employee credentials in the sidebar to view the dashboard.")
    st.stop()

role = st.session_state["role"]
st.title("🏙️ Live US City Zoning Endpoint Dashboard")
st.caption(f"Logged in role: **{role}**")

if role == "admin":
    if st.button("Run endpoint scan now", type="primary"):
        with st.spinner("Checking all monitored endpoints..."):
            scan_results = scan_all_endpoints()
        active_count = sum(status == "ACTIVE" for _, status in scan_results)
        error_count = sum(status == "ERROR" for _, status in scan_results)
        st.success(
            f"Scan complete: {active_count} active, {error_count} error(s), "
            f"{len(scan_results)} endpoint(s) checked."
        )

    with st.expander("Add a city endpoint"):
        with st.form("add_city"):
            city = st.text_input("City")
            county = st.text_input("County")
            state = st.text_input("State name")
            endpoint = st.text_input("Endpoint URL")
            submitted = st.form_submit_button("Add endpoint")
        if submitted:
            if not all(value.strip() for value in (city, county, state, endpoint)):
                st.error("All fields are required.")
            elif not endpoint.startswith(("http://", "https://")):
                st.error("Endpoint must start with http:// or https://.")
            else:
                try:
                    normalized_state = normalize_state(state)
                    with connect() as connection:
                        connection.execute(
                            """
                            INSERT INTO cities (city, county, state, endpoint)
                            VALUES (?, ?, ?, ?)
                            """,
                            (city.strip(), county.strip(), normalized_state, endpoint.strip()),
                        )
                    st.success("City endpoint added.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except sqlite3.IntegrityError:
                    st.error("That endpoint is already being monitored.")

    with st.expander("Import city endpoints from CSV or Excel"):
        st.caption("Required columns: City, County, State, and Endpoint Links. New_Date is optional.")
        uploaded_file = st.file_uploader(
            "Upload a .csv or .xlsx file",
            type=["csv", "xlsx"],
            key="city_data_file",
        )
        if uploaded_file is not None and st.button("Import endpoints", type="primary"):
            try:
                with connect() as connection:
                    added, errors = import_cities_from_upload(uploaded_file, connection)
                st.success(f"Imported {added} endpoint(s).")
                if errors:
                    st.warning("Some rows were not imported:\n\n" + "\n".join(errors))
                if added:
                    st.rerun()
            except (ValueError, ImportError) as error:
                st.error(f"Could not import the file: {error}")

with st.expander("Validate zoning data accuracy"):
    st.caption(
        "Upload a zoning CSV to compare endpoint dates and validate Zone_Code_FN "
        "field names. The uploaded file is processed in this session and is not modified."
    )
    validation_file = st.file_uploader(
        "Upload a CSV file",
        type=["csv"],
        key="validation_data_file",
    )
    run_validation = st.button(
        "Run validation",
        type="primary",
        use_container_width=True,
        key="run_validation",
    )

    if validation_file is not None:
        try:
            validation_input = pd.read_csv(validation_file, encoding="utf-8-sig")
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            st.error(f"Could not read this CSV: {error}")
        else:
            column_problems = validate_input_columns(validation_input)
            if column_problems:
                st.error("This CSV cannot be processed:")
                for problem in column_problems:
                    st.error(problem)
            else:
                st.info(
                    f"Loaded **{len(validation_input):,} rows** and "
                    f"**{len(validation_input.columns):,} columns**."
                )
                with st.expander("Preview uploaded data"):
                    st.dataframe(
                        validation_input.head(10),
                        use_container_width=True,
                        hide_index=True,
                    )

                if run_validation:
                    progress_bar = st.progress(0, text="Starting validation...")
                    progress_status = st.empty()

                    def update_validation_progress(current, total, message):
                        fraction = current / total if total else 0
                        progress_bar.progress(
                            min(fraction, 1.0),
                            text=message,
                        )
                        progress_status.caption(message)

                    try:
                        with st.spinner("Checking endpoints and comparing values..."):
                            report = validate_data(
                                validation_input,
                                progress=update_validation_progress,
                            )
                        progress_bar.progress(1.0, text="Validation complete")
                        progress_status.success("Validation finished successfully.")
                        st.session_state["validation_report_df"] = report
                    except (SystemExit, ValueError, KeyError) as error:
                        progress_bar.empty()
                        progress_status.empty()
                        st.error(str(error))

    validation_report = st.session_state.get("validation_report_df")
    if validation_report is not None:
        is_zone = (
            validation_report["source"]
            .fillna("")
            .str.contains("Zone_Code_FN", case=False, regex=False)
            | validation_report["issue"]
            .fillna("")
            .str.contains("Zone_Code_FN", case=False, regex=False)
            | validation_report["issue"]
            .fillna("")
            .str.startswith("Zone name changed:", na=False)
        )
        is_change = validation_report["updation status"].eq("Updation")
        is_review = validation_report["issue"].fillna("").ne("")
        date_changes = validation_report[is_change & ~is_zone]
        zone_changes = validation_report[is_change & is_zone]
        date_reviews = validation_report[is_review & ~is_zone]
        zone_reviews = validation_report[is_review & is_zone]

        st.subheader("Validation summary")
        metrics = st.columns(5)
        metrics[0].metric("Report items", f"{len(validation_report):,}")
        metrics[1].metric("Date changes", f"{len(date_changes):,}")
        metrics[2].metric("Zone changes", f"{len(zone_changes):,}")
        metrics[3].metric("Date reviews", f"{len(date_reviews):,}")
        metrics[4].metric("Zone reviews", f"{len(zone_reviews):,}")
        st.download_button(
            "Download complete report",
            validation_report.to_csv(index=False).encode("utf-8-sig"),
            file_name="Report.csv",
            mime="text/csv",
            key="download-complete-validation-report",
        )

        validation_tabs = st.tabs(
            [
                f"All results ({len(validation_report)})",
                f"Date changes ({len(date_changes)})",
                f"Zone changes ({len(zone_changes)})",
                f"Date reviews ({len(date_reviews)})",
                f"Zone reviews ({len(zone_reviews)})",
            ]
        )

        def show_validation_report(data, key):
            if data.empty:
                st.success("No items in this view.")
                return
            st.dataframe(
                data,
                column_config={
                    "issue": st.column_config.TextColumn(
                        "issue",
                        width=500,
                        help="Full issue details for this report item",
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )
            issues = data[data["issue"].fillna("").ne("")]
            if not issues.empty:
                with st.expander(f"View full issue details ({len(issues)})"):
                    for _, row in issues.iterrows():
                        location = f"CSV line {row['csv_line']} - {row['city']}"
                        st.markdown(f"**{location}**")
                        st.write(row["issue"])
            st.download_button(
                "Download this view",
                data.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{key}.csv",
                mime="text/csv",
                key=f"download-validation-{key}",
            )

        with validation_tabs[0]:
            show_validation_report(validation_report, "complete-report")
        with validation_tabs[1]:
            show_validation_report(date_changes, "date-changes")
        with validation_tabs[2]:
            show_validation_report(zone_changes, "zone-changes")
        with validation_tabs[3]:
            show_validation_report(date_reviews, "date-reviews")
        with validation_tabs[4]:
            show_validation_report(zone_reviews, "zone-reviews")

st.subheader("Monitored Cities & Update Logs")
cities = load_cities()
if cities.empty:
    st.info("No city endpoints have been added yet.")
else:
    st.dataframe(cities, use_container_width=True, hide_index=True)
