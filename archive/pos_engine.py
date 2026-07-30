import database
import receipt_engine
import audit_log

class POSEngine:
    def __init__(self):
        self.cart = []
        self.patient_id = None
        
    def set_patient(self, patient_id):
        self.patient_id = patient_id
        
    def scan_barcode(self, barcode: str):
        product = database.get_product_by_internal_barcode(barcode)
        if not product:
            product = database.get_product_by_barcode(barcode)
            
        if product:
            # Ensure not already expired or check rules (simplified)
            item = {
                "id": product[0],
                "product_name": product[1],
                "price_at_time": product[2],
                "internal_barcode": product[4],
                "vendor": product[8],
                "expiry_date": product[6],
                "quantity": 1
            }
            self.cart.append(item)
            return True, product
        return False, None
        
    def remove_from_cart(self, index: int):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
            
    def clear_cart(self):
        self.cart.clear()
        self.patient_id = None
        
    def get_total(self):
        return sum(item["price_at_time"] * item["quantity"] for item in self.cart)
        
    def checkout(self, payment_method: str):
        if not self.cart:
            return False, "Cart is empty"
            
        try:
            database.create_receipt(payment_method, self.cart, self.patient_id)
            
            # Find the last receipt ID
            conn = database.sqlite3.connect(database.get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM receipts ORDER BY id DESC LIMIT 1")
            receipt_id = cursor.fetchone()[0]
            conn.close()
            
            receipt_file = receipt_engine.generate_receipt(receipt_id, payment_method, self.cart, self.get_total())
            
            audit_log.log_action("CHECKOUT", f"Receipt ID {receipt_id} created for ${self.get_total():.2f}")
            
            self.clear_cart()
            return True, f"Checkout successful. Receipt saved to {receipt_file}"
        except Exception as e:
            return False, f"Checkout failed: {str(e)}"
