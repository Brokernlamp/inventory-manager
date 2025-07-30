import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # Load the .env file

def get_connection():
    return psycopg2.connect(
        host=os.environ.get("PGHOST"),
        database=os.environ.get("PGDATABASE"),
        user=os.environ.get("PGUSER"),
        password=os.environ.get("PGPASSWORD"),
        port=os.environ.get("PGPORT", 5432),
        sslmode="require"
    )
