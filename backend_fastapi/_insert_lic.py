import sqlite3
from datetime import datetime, timedelta, timezone

db_path = r'C:\Users\Online\AppData\Roaming\com.pharmacy.suite\pharmacy.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in c.fetchall()]
print("Tables:", tables)

if 'licenses' not in tables:
    print("Creating licenses table...")
    c.execute("""
        CREATE TABLE licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT,
            expires_at TEXT,
            subscription_id TEXT,
            hardware_id TEXT,
            offline_until TEXT
        )
    """)

# Check existing
c.execute("SELECT * FROM licenses")
existing = c.fetchall()
print(f"Existing licenses: {len(existing)}")
for r in existing:
    print(f"  {r}")

now = datetime.now(timezone.utc).isoformat()
offline_until = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
expires = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

c.execute("""
    INSERT OR REPLACE INTO licenses (license_key, email, status, created_at, expires_at, subscription_id, hardware_id, offline_until)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "PHARM-A1B2-C3D4-E5F6",
    "admin@pharmacy.local",
    "active",
    now,
    expires,
    "sub_dev_001",
    None,
    offline_until,
))

conn.commit()
print("\nLicense inserted: PHARM-A1B2-C3D4-E5F6")

c.execute("SELECT * FROM licenses")
for r in c.fetchall():
    print(f"  {r}")

conn.close()
