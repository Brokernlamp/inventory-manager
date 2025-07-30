# app.py
import streamlit as st
from db_config import get_connection

st.title("📦 Inventory Viewer")

conn = get_connection()

if conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM products;")
    rows = cur.fetchall()

    if rows:
        st.write("### Product List:")
        for row in rows:
            st.json(row)
    else:
        st.info("No products found.")
else:
    st.error("❌ Failed to connect to the database.")
