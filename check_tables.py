import sqlite3
import os

# Point to the Flask instance folder
DB_PATH = os.path.join('instance', 'cms.db')

print(f"Looking for database at: {os.path.abspath(DB_PATH)}")

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found at {DB_PATH}")
    print("   Run 'python setup_db.py' first.")
    exit(1)

print(f"✅ Database found ({os.path.getsize(DB_PATH)} bytes)")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("\nTables in database:")
for table in tables:
    print(f"  - {table[0]}")

conn.close()