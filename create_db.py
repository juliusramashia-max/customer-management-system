from app import app
from database import db

def create_database():
    """Create all database tables."""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("✅ Database tables created successfully!")
        print("   Tables created:")
        
        # Show what tables were created
        from sqlite3 import connect
        conn = connect('cms.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            print(f"      - {table[0]}")
        conn.close()

if __name__ == '__main__':
    create_database()