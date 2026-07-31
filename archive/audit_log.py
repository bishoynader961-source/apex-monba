import sqlite3
import os
from datetime import datetime
import database


def init_audit_db():
    conn = sqlite3.connect(database.get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            user_pin TEXT DEFAULT '',
            details TEXT DEFAULT ''
        )
    """)
    cursor.execute("PRAGMA table_info(audit_logs)")
    columns = [row[1] for row in cursor.fetchall()]
    if "user_pin" not in columns:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN user_pin TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def log_action(action: str, details: str = "", user_pin: str = ""):
    init_audit_db()
    conn = sqlite3.connect(database.get_db_path())
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO audit_logs (timestamp, action, user_pin, details)
        VALUES (?, ?, ?, ?)
    """, (timestamp, action, user_pin, details))
    conn.commit()
    conn.close()


def get_logs(limit=100, search_query=""):
    init_audit_db()
    conn = sqlite3.connect(database.get_db_path())
    cursor = conn.cursor()
    if search_query:
        like_pattern = f"%{search_query}%"
        cursor.execute("""
            SELECT timestamp, action, user_pin, details FROM audit_logs
            WHERE action LIKE ? OR details LIKE ? OR user_pin LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        """, (like_pattern, like_pattern, like_pattern, limit))
    else:
        cursor.execute(
            "SELECT timestamp, action, user_pin, details FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
    rows = cursor.fetchall()
    conn.close()
    return rows
