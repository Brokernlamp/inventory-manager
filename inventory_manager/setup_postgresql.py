
"""
PostgreSQL Setup Script for Replit

To use PostgreSQL on Replit:
1. Go to the Secrets tab in your Replit
2. Add these environment variables:
   - PGHOST: Your PostgreSQL host (e.g., from Neon, Supabase, or other providers)
   - PGPORT: PostgreSQL port (usually 5432)
   - PGUSER: Your PostgreSQL username
   - PGPASSWORD: Your PostgreSQL password
   - PGDATABASE: Your main database name

For a free PostgreSQL database, you can use:
- Neon (https://neon.tech/) - Free tier with 3GB storage
- Supabase (https://supabase.com/) - Free tier with 500MB storage
- ElephantSQL (https://www.elephantsql.com/) - Free tier with 20MB storage

This script will help you test the connection.
"""

import os
import psycopg2
from db_config import PostgreSQLDB

def test_postgresql_connection():
    """Test PostgreSQL connection"""
    required_vars = ['PGHOST', 'PGUSER', 'PGPASSWORD']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Missing environment variables: {', '.join(missing_vars)}")
        print("Please add them to your Replit Secrets.")
        return False
    
    try:
        # Test connection to postgres database
        conn = psycopg2.connect(
            host=os.environ.get('PGHOST'),
            port=os.environ.get('PGPORT', '5432'),
            database='postgres',
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD')
        )
        
        cursor = conn.cursor()
        cursor.execute('SELECT version()')
        version = cursor.fetchone()[0]
        print(f"PostgreSQL connection successful!")
        print(f"Version: {version}")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PostgreSQL connection failed: {e}")
        return False

def create_sample_user_database():
    """Create a sample user database"""
    db = PostgreSQLDB('inventory_sample_user')
    
    if db.create_database():
        if db.init_tables():
            print("Sample database created and initialized successfully!")
        else:
            print("Failed to initialize tables")
    else:
        print("Failed to create database")

if __name__ == '__main__':
    print("Testing PostgreSQL connection...")
    if test_postgresql_connection():
        create_sample_user_database()
