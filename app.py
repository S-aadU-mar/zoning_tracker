import sqlite3

import pandas as pd
import streamlit as st

from database import authenticate, connect, initialize_database, normalize_state
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

st.subheader("Monitored Cities & Update Logs")
cities = load_cities()
if cities.empty:
    st.info("No city endpoints have been added yet.")
else:
    st.dataframe(cities, use_container_width=True, hide_index=True)
