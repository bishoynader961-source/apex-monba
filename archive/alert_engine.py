import threading
import time
import database
import customtkinter as ctk

class AlertEngine:
    def __init__(self, check_interval_minutes=30):
        self.interval = check_interval_minutes
        self.listeners = []
        self._running = False
        
    def add_listener(self, callback):
        self.listeners.append(callback)
        
    def start(self):
        if self._running:
            return
        self._running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self._running = False
        
    def _run_loop(self):
        # Initial wait to let app startup finish
        time.sleep(5)
        while self._running:
            try:
                self._check_alerts()
            except Exception as e:
                print(f"AlertEngine Error: {e}")
            # Sleep in small chunks to allow quick exit
            for _ in range(self.interval * 60):
                if not self._running:
                    break
                time.sleep(1)
                
    def _check_alerts(self):
        metrics = database.get_dashboard_metrics()
        low_stock = metrics.get('low_stock_count', 0)
        expiring_30 = metrics.get('expiring_30', 0)
        
        alerts = []
        if low_stock > 0:
            alerts.append(f"{low_stock} items are low in stock.")
        if expiring_30 > 0:
            alerts.append(f"{expiring_30} batches are expiring within 30 days.")
            
        if alerts:
            for listener in self.listeners:
                listener(alerts)

# Singleton instance
engine = AlertEngine()

def start_alert_engine():
    engine.start()
