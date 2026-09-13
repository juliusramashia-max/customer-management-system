"""Display all registered users in the database."""
from app import app
from models import User

with app.app_context():
    users = User.query.all()
    print(f"\n{'=' * 60}")
    print(f"REGISTERED USERS: {len(users)}")
    print(f"{'=' * 60}\n")

    if not users:
        print("   (no users registered yet)")
    else:
        for user in users:
            print(f"   ID:         {user.id}")
            print(f"   Email:      {user.email}")
            print(f"   Created:    {user.created_at}")
            print(f"   Hash:       {user.password_hash[:40]}...")
            print(f"   {'-' * 50}")

    print(f"\n   Total: {len(users)} user(s)")
    print(f"{'=' * 60}\n")