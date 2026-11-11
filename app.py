import streamlit as st
import sqlite3

st.set_page_config(page_title="Zoning Tracker", layout="wide")

# Employee Login System
st.sidebar.title("Employee Portal Login")
user = st.sidebar.text_input("Username")
pwd = st.sidebar.text_input("Password", type="password")

if st.sidebar.button("Login"):
    conn = sqlite3.connect("zoning.db")
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE username=? AND password=?", (user, pwd))
    result = c.fetchone()
    if result:
        st.session_state["role"] = result[0]
        st.sidebar.success(f"Logged in as {result[0].upper()}")
    else:
        st.sidebar.error("Invalid Username or Password")

# Access Guard
if "role" not in st.session_state:
    st.info("Please enter your employee credentials in the sidebar to view the dashboard.")
    st.stop()

# Main Dashboard Content
st.title("🏙️ Live US City Zoning Endpoint Dashboard")
st.write(f"Logged in Role: **{st.session_state['role']}**")

if st.session_state["role"] == "admin":
    st.header("Admin Controls")
    st.button("➕ Add New City Endpoint")

st.subheader("Monitored Cities & Update Logs")
# Query database and show cities table
conn = sqlite3.connect("zoning.db")
cities = conn.execute("SELECT city, county, state, status FROM cities").fetchall()
st.dataframe(cities)
