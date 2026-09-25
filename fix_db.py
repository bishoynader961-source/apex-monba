import re

db_path = r'E:\my progam pharmacy\backend_fastapi\app\core\database.py'
with open(db_path, 'r', encoding='utf-8') as f:
    text = f.read()

migration = '''
    # ── v26: Add custom_fields JSON to patients ───────────
    if version < 26:
        if not await _table_has_column(conn, "patients", "custom_fields"):
            await conn.exec_driver_sql(
                "ALTER TABLE patients ADD COLUMN custom_fields TEXT"
            )
        version = 26

    await conn.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")
'''
text = re.sub(
    r'    await conn\.exec_driver_sql\(f"PRAGMA user_version=\{SCHEMA_VERSION\}"\)',
    migration,
    text
)

text = re.sub(
    r'SCHEMA_VERSION = 25',
    'SCHEMA_VERSION = 26',
    text
)

with open(db_path, 'w', encoding='utf-8') as f:
    f.write(text)
