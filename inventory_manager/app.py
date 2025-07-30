import streamlit as st
from db_config import get_connection

st.title("📦 Inventory Viewer")

conn = get_connection()

if conn:
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM products;")
        rows = cur.fetchall()

        st.success("✅ Connected to database and query executed")

        if rows:
            st.write("### Product List:")
            for row in rows:
                st.json(row)
        else:
            st.warning("⚠️ Table `products` is empty.")
    except Exception as e:
        st.error(f"❌ Query failed: {e}")
else:
    st.error("❌ Failed to connect to the database.")
