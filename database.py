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

    conn.commit()
    conn.close()

# --- Products ---

def add_product(name: str, price: float, manufacturer_barcode: str, internal_unique_barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status)
        VALUES (?, ?, ?, ?, 'In Stock')
    """, (name, price, manufacturer_barcode, internal_unique_barcode))
    conn.commit()
    conn.close()

def get_all_products():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status FROM products")
    rows = cursor.fetchall()
    conn.close()
    return rows

def search_products(query: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    like_query = f"%{query}%"
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status 
        FROM products
        WHERE manufacturer_barcode LIKE ? 
           OR internal_unique_barcode LIKE ?
           OR name LIKE ?
    """, (like_query, like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_product_by_barcode(barcode: str):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode, status 
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
        SELECT id, name, price, manufacturer_barcode, internal_unique_barcode 
        FROM products 
        WHERE manufacturer_barcode = ? OR internal_unique_barcode = ?
    """, (barcode, barcode))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        raise ValueError("Product not found.")
        
    product_id, name, price, mfg_barcode, int_barcode = product
    
    # Insert to sold_items
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO sold_items (item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale)
        VALUES (?, ?, ?, ?, ?)
    """, (name, price, mfg_barcode, int_barcode, timestamp))
    
    # Delete from products
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    
    conn.commit()
    conn.close()

def reverse_sale(sold_item_id: int):
    """Moves an item from sold_items back to products."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, item_name, price, manufacturer_barcode, internal_barcode 
        FROM sold_items 
        WHERE id = ?
    """, (sold_item_id,))
    sold_item = cursor.fetchone()
    
    if not sold_item:
        conn.close()
        raise ValueError("Sold item not found.")
        
    sold_id, name, price, mfg_barcode, int_barcode = sold_item
    
    # Insert back to products
    cursor.execute("""
        INSERT INTO products (name, price, manufacturer_barcode, internal_unique_barcode, status)
        VALUES (?, ?, ?, ?, 'In Stock')
    """, (name, price, mfg_barcode, int_barcode))
    
    # Delete from sold_items
    cursor.execute("DELETE FROM sold_items WHERE id = ?", (sold_item_id,))
    
    conn.commit()
    conn.close()

def get_sold_items():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT id, item_name, price, manufacturer_barcode, internal_barcode, timestamp_of_sale FROM sold_items ORDER BY timestamp_of_sale DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

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
