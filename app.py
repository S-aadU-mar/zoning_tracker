import sqlite3

import pandas as pd
import streamlit as st

from database import authenticate, connect, initialize_database


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
    with st.expander("Add a city endpoint"):
        with st.form("add_city"):
            city = st.text_input("City")
            county = st.text_input("County")
            state = st.text_input("State", max_chars=2)
            endpoint = st.text_input("Endpoint URL")
            submitted = st.form_submit_button("Add endpoint")
        if submitted:
            if not all(value.strip() for value in (city, county, state, endpoint)):
                st.error("All fields are required.")
            elif not endpoint.startswith(("http://", "https://")):
                st.error("Endpoint must start with http:// or https://.")
            else:
                try:
                    with connect() as connection:
                        connection.execute(
                            """
                            INSERT INTO cities (city, county, state, endpoint)
                            VALUES (?, ?, ?, ?)
                            """,
                            (city.strip(), county.strip(), state.strip().upper(), endpoint.strip()),
                        )
                    st.success("City endpoint added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That endpoint is already being monitored.")

st.subheader("Monitored Cities & Update Logs")
cities = load_cities()
if cities.empty:
    st.info("No city endpoints have been added yet.")
else:
    st.dataframe(cities, use_container_width=True, hide_index=True)
