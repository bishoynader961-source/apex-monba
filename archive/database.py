import sqlite3
import os
import shutil
from datetime import datetime
from collections import defaultdict
import barcode_logic
from path_utils import get_resource_path

def get_db_path():
    config = barcode_logic.load_config()
    return config.get("db_path", get_resource_path("pharmacy.db"))

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

    # Receipts table (Checkout & Receipts module)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'Cash',
            patient_id INTEGER DEFAULT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE receipts ADD COLUMN patient_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    # Receipt Items table (line items per receipt)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receipt_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price_at_time REAL NOT NULL,
            internal_barcode TEXT DEFAULT '',
            vendor TEXT DEFAULT '',
            expiry_date TEXT DEFAULT '',
            FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
        )
    """)

    # Patients table (CRM)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    # Patient custom fields (EAV pattern for user-defined metadata)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT DEFAULT '',
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )
    """)

    # M49 migration: add batch tracking columns to receipt_items if missing
    cursor.execute("PRAGMA table_info(receipt_items)")
    ri_cols = {row[1] for row in cursor.fetchall()}
    for col, default in [("internal_barcode", ""), ("vendor", ""), ("expiry_date", "")]:
        if col not in ri_cols:
            try:
                cursor.execute(f"ALTER TABLE receipt_items ADD COLUMN {col} TEXT DEFAULT '{default}'")
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


def get_all_in_stock_batches(sort_by: str = 'expiry_date'):
    """Return every individual in-stock product as its own row — flat inventory view.
    Returns: [(id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name)]
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    valid_sorts = {
        'expiry_date': 'expiry_date ASC, name ASC',
        'manufacture_date': 'manufacture_date DESC, name ASC',
        'name': 'name ASC, expiry_date ASC',
        'vendor': 'vendor_name ASC, name ASC',
    }
    order = valid_sorts.get(sort_by, 'expiry_date ASC, name ASC')
    cursor.execute(f"""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
        ORDER BY {order}
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def search_all_batches(query: str):
    """Search in-stock products across all fields — flat results.
    Returns same shape as get_all_in_stock_batches().
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND (name LIKE ? OR manufacturer_barcode LIKE ? OR internal_unique_barcode LIKE ?
               OR vendor_name LIKE ? OR expiry_date LIKE ?)
        ORDER BY name ASC, expiry_date ASC
    """, (like_query, like_query, like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_product_by_internal_barcode(internal_barcode: str):
    """Fetch a single product row by its internal_unique_barcode."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE internal_unique_barcode = ? AND status = 'In Stock'
    """, (internal_barcode,))
    row = cursor.fetchone()
    conn.close()
    return row


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

def get_expiring_batches(exclude_names=None):
    from datetime import date, timedelta
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND expiry_date != ''
        ORDER BY expiry_date ASC
    """)
    all_rows = cursor.fetchall()
    conn.close()

    today = date.today()
    result = []
    exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
    for row in all_rows:
        if exclude_set and row[1].lower().strip() in exclude_set:
            continue
        raw_expiry = row[6]
        try:
            normalized = raw_expiry.replace('/', '-')
            parts = normalized.split('-')
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            result.append((exp_date, row))
        except (ValueError, IndexError):
            continue
    return result

def get_batches_expiring_within(days: int, exclude_names=None):
    """Return all in-stock batches expiring within N days from today, AND already expired batches.
    Handles mixed date formats (YYYY/M/D, YYYY-MM-DD) by normalizing
    in Python after fetching. Returns: [(id, name, price, manufacturer_barcode,
    internal_unique_barcode, status, expiry_date, manufacture_date, vendor_name)]
    Sorted by expiry_date ASC (FIFO).
    """
    from datetime import date, timedelta
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
               status, expiry_date, manufacture_date, vendor_name
        FROM products
        WHERE status = 'In Stock'
          AND expiry_date != ''
        ORDER BY expiry_date ASC
    """)
    all_rows = cursor.fetchall()
    conn.close()

    today = date.today()
    cutoff = today + timedelta(days=days)
    result = []
    exclude_set = set(n.lower().strip() for n in exclude_names) if exclude_names else set()
    for row in all_rows:
        if exclude_set and row[1].lower().strip() in exclude_set:
            continue
        raw_expiry = row[6]
        try:
            normalized = raw_expiry.replace('/', '-')
            parts = normalized.split('-')
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            if exp_date <= cutoff:
                result.append(row)
        except (ValueError, IndexError):
            continue
    return result

def get_expiring_counts_by_vendor(days: int, exclude_names=None):
    """Return expiring batch counts grouped by vendor_name.
    Uses the same filtering logic as get_batches_expiring_within.
    Returns: [(vendor_name, count)] sorted by count DESC.
    """
    batches = get_batches_expiring_within(days, exclude_names=exclude_names)
    counts = {}
    for row in batches:
        vendor = row[8] or "N/A"
        counts[vendor] = counts.get(vendor, 0) + 1
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)

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

# --- Checkout & Receipts ---

def create_receipt(payment_method: str, items: list[dict], patient_id: int = None):
    """Create a receipt with line items. Each item dict:
        {product_name, quantity, price_at_time, internal_barcode, vendor, expiry_date}.
    Atomically: inserts receipt + receipt_items, deletes sold products from inventory.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_amount = sum(item["quantity"] * item["price_at_time"] for item in items)
        cursor.execute(
            "INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id) VALUES (?, ?, ?, ?)",
            (timestamp, total_amount, payment_method, patient_id)
        )
        receipt_id = cursor.lastrowid
        for item in items:
            cursor.execute("""
                INSERT INTO receipt_items
                    (receipt_id, product_name, quantity, price_at_time,
                     internal_barcode, vendor, expiry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_id, item["product_name"], item["quantity"], item["price_at_time"],
                item.get("internal_barcode", ""), item.get("vendor", ""),
                item.get("expiry_date", "")
            ))
        # Deduct stock: delete the exact batch by internal_unique_barcode
        for item in items:
            barcode = item.get("internal_barcode", "")
            if barcode:
                # Precise batch-level deduction
                cursor.execute("""
                    SELECT id FROM products
                    WHERE internal_unique_barcode = ? AND status = 'In Stock'
                """, (barcode,))
                row = cursor.fetchone()
                if not row:
                    conn.rollback()
                    raise ValueError(
                        f"Batch '{barcode}' for '{item['product_name']}' not found in stock."
                    )
                # Verify requested qty is 1 (serialized model: 1 row = 1 box)
                if item["quantity"] != 1:
                    conn.rollback()
                    raise ValueError(
                        f"Serialized model allows qty=1 per batch. "
                        f"Got qty={item['quantity']} for '{item['product_name']}'."
                    )
                cursor.execute("DELETE FROM products WHERE id = ?", (row[0],))
            else:
                # Fallback: name-based deduction (legacy path)
                cursor.execute("""
                    SELECT id FROM products
                    WHERE name = ? AND status = 'In Stock'
                    ORDER BY id ASC
                    LIMIT ?
                """, (item["product_name"], item["quantity"]))
                rows = cursor.fetchall()
                if len(rows) < item["quantity"]:
                    conn.rollback()
                    raise ValueError(
                        f"Insufficient stock for '{item['product_name']}': "
                        f"need {item['quantity']}, have {len(rows)}"
                    )
                for row in rows:
                    cursor.execute("DELETE FROM products WHERE id = ?", (row[0],))
        conn.commit()
        return receipt_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_receipts():
    """Return all receipts ordered by most recent first."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, total_amount, payment_method FROM receipts ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_receipt_items(receipt_id: int):
    """Return line items for a given receipt."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, receipt_id, product_name, quantity, price_at_time,
               COALESCE(internal_barcode, '') as internal_barcode,
               COALESCE(vendor, '') as vendor,
               COALESCE(expiry_date, '') as expiry_date
        FROM receipt_items WHERE receipt_id = ?
    """, (receipt_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_receipt_items_flat():
    """Flat view of all sold items across all receipts — used by Sales Report.
    Returns: [(receipt_item_id, receipt_id, product_name, quantity, price_at_time,
               line_total, receipt_timestamp, payment_method,
               internal_barcode, vendor, expiry_date)]
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
               (ri.quantity * ri.price_at_time) as line_total,
               r.timestamp, r.payment_method,
               COALESCE(ri.internal_barcode, '') as internal_barcode,
               COALESCE(ri.vendor, '') as vendor,
               COALESCE(ri.expiry_date, '') as expiry_date
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        ORDER BY r.timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_receipt_items_for_date(date_str: str):
    """Receipt items filtered to a specific date (YYYY-MM-DD)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.id, ri.receipt_id, ri.product_name, ri.quantity, ri.price_at_time,
               (ri.quantity * ri.price_at_time) as line_total,
               r.timestamp, r.payment_method,
               COALESCE(ri.internal_barcode, '') as internal_barcode,
               COALESCE(ri.vendor, '') as vendor,
               COALESCE(ri.expiry_date, '') as expiry_date
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE r.timestamp LIKE ?
        ORDER BY r.timestamp DESC
    """, (f"{date_str}%",))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_receipt_items_grouped_by_date():
    """All receipt items grouped by date — used by Sales Report parent/child treeview.
    Returns: {date_str: [(receipt_item_id, receipt_id, product_name, quantity,
              price_at_time, line_total, timestamp, payment_method), ...]}
    """
    flat = get_all_receipt_items_flat()
    grouped = defaultdict(list)
    for r in flat:
        # r[6] = timestamp like "2026-07-19 14:30:00"
        date_part = r[6][:10] if r[6] and len(r[6]) >= 10 else "Unknown"
        grouped[date_part].append(r)
    return grouped


def get_receipts_total_for_date(date_str: str):
    """Sum of receipt totals for a specific date."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(SUM(total_amount), 0.0) FROM receipts WHERE timestamp LIKE ?",
        (f"{date_str}%",)
    )
    total = cursor.fetchone()[0]
    conn.close()
    return total


def reverse_receipt_item(receipt_item_id: int):
    """Reverse a single receipt line item: restore product to inventory, remove the item,
    and update the receipt total. If the receipt has no remaining items, delete it.
    Uses stored internal_barcode, vendor, expiry_date from receipt_items for accurate restore.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")

        # Get the receipt item (including batch metadata)
        cursor.execute("""
            SELECT id, receipt_id, product_name, quantity, price_at_time,
                   COALESCE(internal_barcode, '') as internal_barcode,
                   COALESCE(vendor, '') as vendor,
                   COALESCE(expiry_date, '') as expiry_date
            FROM receipt_items WHERE id = ?
        """, (receipt_item_id,))
        item = cursor.fetchone()
        if not item:
            conn.rollback()
            raise ValueError("Receipt item not found.")

        (_, receipt_id, product_name, quantity, price_at_time,
         stored_barcode, stored_vendor, stored_expiry) = item

        # Restore products: add `quantity` units back to inventory
        import barcode_logic as _bl
        for _ in range(quantity):
            if stored_barcode:
                unique_barcode = stored_barcode
            else:
                unique_barcode = _bl.generate_internal_barcode(stored_vendor or "N/A")
            cursor.execute("""
                INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode,
                                      status, expiry_date, manufacture_date, vendor_name)
                VALUES (?, ?, '', ?, 'In Stock', ?, '', ?)
            """, (product_name, price_at_time, unique_barcode,
                  stored_expiry, stored_vendor or 'N/A'))

        # Remove the receipt item
        cursor.execute("DELETE FROM receipt_items WHERE id = ?", (receipt_item_id,))

        # Update receipt total
        line_total = quantity * price_at_time
        cursor.execute(
            "UPDATE receipts SET total_amount = total_amount - ? WHERE id = ?",
            (line_total, receipt_id)
        )

        # If receipt has no remaining items, delete it
        cursor.execute("SELECT COUNT(*) FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
        remaining = cursor.fetchone()[0]
        if remaining == 0:
            cursor.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


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


# --- Dashboard & Analytics ---

def get_dashboard_metrics():
    """Returns a dict with all dashboard KPI metrics.
    Optimized: runs all scalar queries in a single connection, then
    delegates expiry/low-stock to their existing helpers.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM products WHERE status = 'In Stock'")
    total_in_stock = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM products WHERE status = 'In Stock'")
    total_inventory_value = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sold_items")
    total_sold = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items")
    total_revenue = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT name) FROM products WHERE status = 'In Stock'")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT vendor_name) FROM products WHERE status = 'In Stock' AND vendor_name != 'N/A'")
    total_vendors = cursor.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(price), 0.0) FROM sold_items WHERE timestamp_of_sale LIKE ?", (f"{today}%",))
    todays_sales = cursor.fetchone()[0]

    conn.close()

    expiring = get_expiring_batches()
    from datetime import date, timedelta
    today_date = date.today()
    c30 = c60 = c90 = 0
    for exp_date, _row in expiring:
        delta = (exp_date - today_date).days
        if delta <= 30:
            c30 += 1
        elif delta <= 60:
            c60 += 1
        elif delta <= 90:
            c90 += 1

    low_stock = get_low_stock_products()

    return {
        "total_in_stock": total_in_stock,
        "total_inventory_value": total_inventory_value,
        "total_sold": total_sold,
        "total_revenue": total_revenue,
        "total_products": total_products,
        "total_vendors": total_vendors,
        "todays_sales": todays_sales,
        "expiring_30": c30,
        "expiring_60": c60,
        "expiring_90": c90,
        "low_stock": low_stock,
        "low_stock_count": len(low_stock),
    }


def get_low_stock_products(threshold=5):
    """Returns products with stock count <= threshold, grouped by name."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, COUNT(*) as qty, MIN(expiry_date) as min_expiry
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        HAVING COUNT(*) <= ?
        ORDER BY qty ASC, name ASC
    """, (threshold,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_top_selling_products(start_date, end_date, limit=10):
    """Returns [(product_name, total_qty, total_revenue)] sorted by qty DESC."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ri.product_name, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
        GROUP BY ri.product_name
        ORDER BY SUM(ri.quantity) DESC
        LIMIT ?
    """, (start_date, end_date, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_sales_analytics(start_date: str, end_date: str) -> dict:
    """Comprehensive sales analytics for a date range.
    Returns a dict with:
        - ranked_products: [(rank, product_name, total_qty, total_revenue, avg_price)]
        - total_items_sold: int
        - total_revenue: float
        - unique_products: int
        - total_transactions: int
        - avg_basket_size: float
    All queries are optimized single-pass against receipt_items + receipts.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ri.product_name,
               SUM(ri.quantity) as total_qty,
               SUM(ri.quantity * ri.price_at_time) as total_revenue,
               ROUND(SUM(ri.quantity * ri.price_at_time) / SUM(ri.quantity), 2) as avg_price
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
        GROUP BY ri.product_name
        ORDER BY total_qty DESC
    """, (start_date, end_date))
    raw_products = cursor.fetchall()

    ranked_products = []
    for rank, (name, qty, revenue, avg_price) in enumerate(raw_products, 1):
        ranked_products.append((rank, name, qty, revenue, avg_price))

    cursor.execute("""
        SELECT COALESCE(SUM(ri.quantity), 0),
               COALESCE(SUM(ri.quantity * ri.price_at_time), 0),
               COUNT(DISTINCT ri.product_name),
               COUNT(DISTINCT r.id)
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN ? AND ?
    """, (start_date, end_date))
    total_items, total_rev, unique_prods, total_txns = cursor.fetchone()

    avg_basket = (total_items / total_txns) if total_txns > 0 else 0.0

    conn.close()

    return {
        "ranked_products": ranked_products,
        "total_items_sold": total_items,
        "total_revenue": total_rev,
        "unique_products": unique_prods,
        "total_transactions": total_txns,
        "avg_basket_size": round(avg_basket, 1),
    }


def get_sales_by_period(period='month'):
    """Returns [(period_label, total_qty, total_revenue)] for charting."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    if period == 'day':
        cursor.execute("""
            SELECT date(r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY date(r.timestamp)
            ORDER BY period DESC
        """)
    elif period == 'week':
        cursor.execute("""
            SELECT strftime('%Y-W%W', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y-W%W', r.timestamp)
            ORDER BY period DESC
        """)
    elif period == 'year':
        cursor.execute("""
            SELECT strftime('%Y', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y', r.timestamp)
            ORDER BY period DESC
        """)
    else:  # month
        cursor.execute("""
            SELECT strftime('%Y-%m', r.timestamp) as period, SUM(ri.quantity), SUM(ri.quantity * ri.price_at_time)
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            GROUP BY strftime('%Y-%m', r.timestamp)
            ORDER BY period DESC
        """)

    rows = cursor.fetchall()
    conn.close()
    return rows


# --- Patients CRM ---

def add_patient(name: str, phone: str = '', email: str = '', custom_fields: dict = None):
    """Insert a new patient with optional custom fields.
    custom_fields: {"Allergies": "Penicillin", "Insurance": "ABC123", ...}
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO patients (name, phone, email, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, email, created_at)
        )
        patient_id = cursor.lastrowid
        if custom_fields:
            for field_name, field_value in custom_fields.items():
                if field_name and field_name.strip():
                    cursor.execute(
                        "INSERT INTO patient_fields (patient_id, field_name, field_value) VALUES (?, ?, ?)",
                        (patient_id, field_name.strip(), field_value)
                    )
        conn.commit()
        return patient_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_all_patients(search_query: str = None):
    """Return all patients with their custom fields.
    Returns: [(patient_id, name, phone, email, created_at, {field_name: field_value, ...})]
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if search_query:
        like_query = f"%{search_query}%"
        cursor.execute("""
            SELECT id, name, phone, email, created_at
            FROM patients
            WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?
            ORDER BY name ASC
        """, (like_query, like_query, like_query))
    else:
        cursor.execute("SELECT id, name, phone, email, created_at FROM patients ORDER BY name ASC")
    patients = cursor.fetchall()

    result = []
    for pid, name, phone, email, created_at in patients:
        cursor.execute(
            "SELECT field_name, field_value FROM patient_fields WHERE patient_id = ?",
            (pid,)
        )
        fields = {row[0]: row[1] for row in cursor.fetchall()}
        result.append((pid, name, phone, email, created_at, fields))

    conn.close()
    return result


def get_patient_by_id(patient_id: int):
    """Return a single patient with custom fields, or None."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, phone, email, created_at FROM patients WHERE id = ?",
        (patient_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    pid, name, phone, email, created_at = row
    cursor.execute(
        "SELECT field_name, field_value FROM patient_fields WHERE patient_id = ?",
        (pid,)
    )
    fields = {r[0]: r[1] for r in cursor.fetchall()}
    conn.close()
    return (pid, name, phone, email, created_at, fields)


def update_patient(patient_id: int, name: str, phone: str = '', email: str = '', custom_fields: dict = None):
    """Update patient core fields and replace all custom fields."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute(
            "UPDATE patients SET name = ?, phone = ?, email = ? WHERE id = ?",
            (name, phone, email, patient_id)
        )
        cursor.execute("DELETE FROM patient_fields WHERE patient_id = ?", (patient_id,))
        if custom_fields:
            for field_name, field_value in custom_fields.items():
                if field_name and field_name.strip():
                    cursor.execute(
                        "INSERT INTO patient_fields (patient_id, field_name, field_value) VALUES (?, ?, ?)",
                        (patient_id, field_name.strip(), field_value)
                    )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_patient(patient_id: int):
    """Delete a patient and all their custom fields (CASCADE)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM patient_fields WHERE patient_id = ?", (patient_id,))
    cursor.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


def get_distinct_patient_field_names():
    """Return sorted list of distinct custom field names ever used.
    Used to populate the CTkComboBox suggestions in the patient dialog.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT field_name FROM patient_fields ORDER BY field_name ASC")
    names = [r[0] for r in cursor.fetchall()]
    conn.close()
    return names
