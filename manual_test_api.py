import requests

BASE = "http://localhost:5000/api/v1/auth"

# Register
r = requests.post(f"{BASE}/register", json={
    "email": "bob@example.com",
    "password": "secret123",
})
print(f"Register: {r.status_code} {r.json()}")

# Duplicate
r = requests.post(f"{BASE}/register", json={
    "email": "bob@example.com",
    "password": "secret123",
})
print(f"Duplicate: {r.status_code} {r.json()}")

# Login
session = requests.Session()
r = session.post(f"{BASE}/login", json={
    "email": "bob@example.com",
    "password": "secret123",
})
print(f"Login: {r.status_code} {r.json()}")

# Wrong password
r = requests.post(f"{BASE}/login", json={
    "email": "bob@example.com",
    "password": "wrong",
})
print(f"Wrong password: {r.status_code} {r.json()}")

# Nonexistent email
r = requests.post(f"{BASE}/login", json={
    "email": "nobody@example.com",
    "password": "wrong",
})
print(f"Nonexistent: {r.status_code} {r.json()}")