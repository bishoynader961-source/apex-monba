import sqlite3

p = "pharmacy.db"
conn = sqlite3.connect(p)
c = conn.cursor()
c.execute("DELETE FROM permissions WHERE feature_key IN ('backup.manage','settings.view')")
c.execute("DELETE FROM role_permissions WHERE permission_id NOT IN (SELECT id FROM permissions)")
c.execute("DELETE FROM users WHERE username='cashTmp'")
conn.commit()
conn.close()
print("prod db reset to 15-permission baseline")
