import sqlite3
import os
import shutil
from datetime import datetime
import barcode_logic

def get_db_path():
    config = barcode_logic.load_config()
    return config.get("db_path", "pharmacy.db")

def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            manufacturer_barcode TEXT NOT NULL,
            internal_unique_barcode TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'In Stock'
        )
    """)
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'In Stock'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN manufacture_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN vendor_name TEXT DEFAULT 'N/A'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE products ADD COLUMN manufacturer_barcode TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Templates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    
    # Check if templates is empty, add defaults
    cursor.execute("SELECT COUNT(*) FROM templates")
    if cursor.fetchone()[0] == 0:
        defaults = [
            ("Aspirin 500mg", 5.99),
            ("Band-Aids (40ct)", 3.49),
            ("Ibuprofen 200mg", 6.50),
            ("Cough Syrup", 8.99)
        ]
        cursor.executemany("INSERT INTO templates (name, price) VALUES (?, ?)", defaults)
        
    # Sold Items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sold_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            manufacturer_barcode TEXT NOT NULL,
            internal_barcode TEXT NOT NULL,
            timestamp_of_sale TEXT NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE sold_items ADD COLUMN vendor_name TEXT DEFAULT 'N/A'")
    except sqlite3.OperationalError:
        pass

    # Receiving Log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receiving_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            date_received TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_cost REAL NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE receiving_log ADD COLUMN barcode TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # Migration M33 complete: legacy barcodes normalized
    cursor.execute("PRAGMA table_info(products)")
    cols = {row[1] for row in cursor.fetchall()}
    expected = {'id', 'name', 'price', 'manufacturer_barcode', 'internal_unique_barcode', 'status', 'expiry_date', 'manufacture_date', 'vendor_name'}
    if not expected.issubset(cols):
        missing = expected - cols
        raise RuntimeError(f"Database schema integrity failure. Missing columns: {missing}")

    conn.commit()
    conn.close()

# --- Products ---

def add_product(name: str, price: float, manufacturer_barcode: str, internal_unique_barcode: str,
                expiry_date: str = '', manufacture_date: str = '', vendor_name: str = 'N/A'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name)
        VALUES (?, ?, ?, ?, 'In Stock', ?, ?, ?)
    """, (name, price, manufacturer_barcode, internal_unique_barcode, expiry_date, manufacture_date, vendor_name))
    conn.commit()
    conn.close()

def get_all_products():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name FROM products")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_product_by_id(product_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products WHERE id = ?
    """, (product_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def search_products(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE manufacturer_barcode LIKE ? 
           OR internal_unique_barcode LIKE ?
           OR name LIKE ?
    """, (like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_grouped_products():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_products_with_vendors():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name, COALESCE(vendor_name, 'N/A') as vendor_name, internal_unique_barcode
        FROM products
        WHERE status = 'In Stock'
        ORDER BY name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_unique_product_names():
    """Single source of truth for product name lists.
    Returns distinct drug names with status='In Stock', alphabetically sorted.
    Mirrors get_grouped_products() — guarantees Receive tab combobox matches Inventory tab exactly.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name
        FROM products
        WHERE status = 'In Stock'
        ORDER BY name ASC
    """)
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def get_product_template(name: str, vendor_name: str = None):

    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
        cursor.execute("""
            SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
            FROM products WHERE name = ? AND vendor_name = ? AND status = 'In Stock' ORDER BY id DESC LIMIT 1
        """, (name, vendor_name.strip()))
    else:
        cursor.execute("""
            SELECT name, price, manufacturer_barcode, expiry_date, manufacture_date
            FROM products WHERE name = ? AND status = 'In Stock' ORDER BY id DESC LIMIT 1
        """, (name,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_products_by_vendor(vendor_name: str = None):
    """Return distinct product names, optionally filtered by vendor."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A':
        cursor.execute("""
            SELECT DISTINCT name FROM products
            WHERE vendor_name = ? AND status = 'In Stock'
            ORDER BY name ASC
        """, (vendor_name.strip(),))
    else:
        cursor.execute("""
            SELECT DISTINCT name FROM products
            WHERE status = 'In Stock'
            ORDER BY name ASC
        """)
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_batches_by_name(drug_name: str, sort_by: str = 'expiry_date'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    valid_sorts = {'expiry_date': 'expiry_date ASC', 'manufacture_date': 'manufacture_date DESC'}
    order = valid_sorts.get(sort_by, 'expiry_date ASC')
    cursor.execute(f"""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE name = ? AND status = 'In Stock'
        ORDER BY {order}
    """, (drug_name,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def search_grouped_products(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(price) as min_price, MAX(price) as max_price
        FROM products
        WHERE status = 'In Stock'
          AND (name LIKE ? OR manufacturer_barcode LIKE ? OR internal_unique_barcode LIKE ?)
        GROUP BY name
        ORDER BY name ASC
    """, (like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_product_dates(product_id: int, expiry_date: str, manufacture_date: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products SET expiry_date = ?, manufacture_date = ? WHERE id = ?
    """, (expiry_date, manufacture_date, product_id))
    conn.commit()
    conn.close()

def update_product_full(product_id: int, name: str, price: float, manufacturer_barcode: str,
                         internal_barcode: str, expiry_date: str, manufacture_date: str,
                         status: str, vendor_name: str = 'N/A'):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products SET name = ?, price = ?, manufacturer_barcode = ?,
               internal_unique_barcode = ?, expiry_date = ?, manufacture_date = ?,
               status = ?, vendor_name = ? WHERE id = ?
    """, (name, price, manufacturer_barcode, internal_barcode, expiry_date, manufacture_date,
          status, vendor_name, product_id))
    cursor.execute("""
        UPDATE receiving_log SET vendor_name = ?, product_name = ? WHERE barcode = ? AND barcode != ''
    """, (vendor_name, name, internal_barcode))
    cursor.execute("""
        UPDATE receiving_log SET total_cost = ? * quantity WHERE barcode = ? AND barcode != ''
    """, (price, internal_barcode))
    conn.commit()
    conn.close()

def get_expiring_batches():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            SUM(CASE WHEN date(expiry_date) <= date('now', '+30 days') THEN 1 ELSE 0 END) as cnt_30,
            SUM(CASE WHEN date(expiry_date) > date('now', '+30 days') AND date(expiry_date) <= date('now', '+60 days') THEN 1 ELSE 0 END) as cnt_60,
            SUM(CASE WHEN date(expiry_date) > date('now', '+60 days') AND date(expiry_date) <= date('now', '+90 days') THEN 1 ELSE 0 END) as cnt_90
        FROM products
        WHERE status = 'In Stock'
          AND expiry_date != ''
          AND date(expiry_date) >= date('now')
          AND date(expiry_date) <= date('now', '+90 days')
    """)
    row = cursor.fetchone()
    conn.close()
    c30 = row[0] or 0
    c60 = row[1] or 0
    c90 = row[2] or 0
    return {'30': c30, '60': c60, '90': c90}

def get_product_by_barcode(barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (barcode, barcode))
    row = cursor.fetchone()
    conn.close()
    return row

def update_product_status(barcode: str, new_status: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products 
        SET status = ?
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (new_status, barcode, barcode))
    conn.commit()
    conn.close()

# --- Sales Logic ---

def mark_item_as_sold(barcode: str):
    """Moves an item from products to sold_items."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # Get the product
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, vendor_name
        FROM products 
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (barcode, barcode))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        raise ValueError("Product not found.")
        
    product_id, name, price, mfg_barcode, int_barcode, vendor_name = product
    
    # Insert to sold_items
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO sold_items (item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale, vendor_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, price, mfg_barcode, int_barcode, timestamp, vendor_name or 'N/A'))
    
    # Delete from products
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    
    conn.commit()
    conn.close()

def reverse_sale(sold_item_id: int):
    """Moves an item from sold_items back to products."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, item_name, price, manufacturer_barcode, internal_barcode, vendor_name
        FROM sold_items 
        WHERE id = ?
    """, (sold_item_id,))
    sold_item = cursor.fetchone()
    
    if not sold_item:
        conn.close()
        raise ValueError("Sold item not found.")
        
    sold_id, name, price, mfg_barcode, int_barcode, vendor_name = sold_item
    
    # Insert back to products
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status, vendor_name)
        VALUES (?, ?, ?, ?, 'In Stock', ?)
    """, (name, price, mfg_barcode, int_barcode, vendor_name or 'N/A'))
    
    # Delete from sold_items
    cursor.execute("DELETE FROM sold_items WHERE id = ?", (sold_item_id,))
    
    conn.commit()
    conn.close()

def get_sold_items():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale,
               COALESCE(vendor_name, 'N/A') as vendor_name
        FROM sold_items
        ORDER BY timestamp_of_sale DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_today_sales_total():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{today}%",))
    total = cursor.fetchone()[0]
    conn.close()
    return total

def get_sales_for_date(date_str: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{date_str}%",))
    total = cursor.fetchone()[0]
    conn.close()
    return total

# --- Templates ---

def get_templates():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM templates ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_template(name: str, price: float):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("INSERT INTO templates (name, price) VALUES (?, ?)", (name, price))
    conn.commit()
    conn.close()

def update_template(template_id: int, name: str, price: float):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("UPDATE templates SET name = ?, price = ? WHERE id = ?", (name, price, template_id))
    conn.commit()
    conn.close()

def delete_template(template_id: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()

# --- Receiving Log ---

def log_shipment(vendor_name: str, product_name: str, date_received: str, quantity: int, total_cost: float, barcode: str = ''):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO receiving_log (vendor_name, product_name, date_received, quantity, total_cost, barcode) VALUES (?, ?, ?, ?, ?, ?)",
        (vendor_name, product_name, date_received, quantity, total_cost, barcode)
    )
    conn.commit()
    conn.close()

def receive_inventory_atomically(vendor_name: str, product_name: str, date_received: str,
                                  quantity: int, total_cost: float,
                                  tpl_price: float, tpl_mfg_barcode: str,
                                  tpl_expiry: str, tpl_mfg_date: str,
                                  barcode_generator,
                                  pre_generated_barcodes=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    last_barcode = ''
    try:
        cursor.execute("BEGIN TRANSACTION")
        for i in range(quantity):
            if pre_generated_barcodes and i < len(pre_generated_barcodes):
                unique_barcode = pre_generated_barcodes[i]
            else:
                unique_barcode = barcode_generator(vendor_name)
            cursor.execute("""
                INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name)
                VALUES (?, ?, ?, ?, 'In Stock', ?, ?, ?)
            """, (product_name, tpl_price, tpl_mfg_barcode, unique_barcode, tpl_expiry, tpl_mfg_date, vendor_name))
            last_barcode = unique_barcode
        cursor.execute(
            "INSERT INTO receiving_log (vendor_name, product_name, date_received, quantity, total_cost, barcode) VALUES (?, ?, ?, ?, ?, ?)",
            (vendor_name, product_name, date_received, quantity, total_cost, last_barcode)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
    return last_barcode

def get_all_receiving_log(filter_date=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if filter_date:
        cursor.execute(
            "SELECT id, vendor_name, product_name, date_received, quantity, total_cost, COALESCE(barcode, '') as barcode FROM receiving_log WHERE date_received = ? ORDER BY date_received DESC",
            (filter_date,))
    else:
        cursor.execute("SELECT id, vendor_name, product_name, date_received, quantity, total_cost, COALESCE(barcode, '') as barcode FROM receiving_log ORDER BY date_received DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_vendor_total_owed(vendor_name: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(total_cost), 0.0) FROM receiving_log WHERE vendor_name = ?", (vendor_name,))
    total = cursor.fetchone()[0]
    conn.close()
    return total

def get_all_vendors():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT vendor_name FROM receiving_log ORDER BY vendor_name ASC")
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

# --- Backup ---
def backup_database(dest_folder: str):
    db_path = get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError("Database file does not exist yet. Please add a product first.")
    
    date_str = datetime.now().strftime("%Y%m%d")
    filename = os.path.basename(db_path)
    if not filename:
        filename = "pharmacy.db"
        
    name, ext = os.path.splitext(filename)
    backup_filename = f"{name}_{date_str}{ext}"
    backup_path = os.path.join(dest_folder, backup_filename)
    
    shutil.copy2(db_path, backup_path)
    return backup_path
