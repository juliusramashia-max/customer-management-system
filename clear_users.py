# clear_users.py
from app import app
from database import db
from models import User

with app.app_context():
    count = User.query.count()
    User.query.delete()
    db.session.commit()
    print(f"Deleted {count} user(s)")