import sqlite3
import os

def check_database():
    """Check if database exists and show its tables."""
    db_path = os.path.join('instance', 'cms.db')
    db_file = db_path
    
    # Check if database file exists
    if not os.path.exists(db_file):
        print(f"❌ Database '{db_file}' not found!")
        print("   Run 'python app.py' first to create the database.")
        return
    
    print(f"✅ Database '{db_file}' found!")
    print("=" * 50)
    
    # Connect to database
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    if not tables:
        print("❌ No tables found in database!")
        print("   Make sure you've run the application with database creation.")
    else:
        print("📋 Tables in database:")
        for table in tables:
            print(f"   - {table[0]}")
    
    print("=" * 50)
    
    # Show schema for each table
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print(f"\n📊 Table: {table_name}")
        print("   Columns:")
        for col in columns:
            print(f"      - {col[1]} ({col[2]})")
    
    conn.close()

if __name__ == '__main__':
    check_database()