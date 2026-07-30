import os
import shutil
import threading
import time
from datetime import datetime
import database
from path_utils import get_resource_path

BACKUP_DIR = get_resource_path("backups")
MAX_BACKUPS = 10

def init_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

def create_backup():
    init_backup_dir()
    db_path = database.get_db_path()
    if not os.path.exists(db_path):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"pharmacy_backup_{timestamp}.db")
    shutil.copy2(db_path, backup_file)
    
    # Cleanup old backups
    try:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("pharmacy_backup_")])
        while len(backups) > MAX_BACKUPS:
            oldest = backups.pop(0)
            try:
                os.remove(os.path.join(BACKUP_DIR, oldest))
            except OSError:
                pass
    except OSError:
        pass
            
    return backup_file

def start_background_backup(interval_minutes=60):
    def _backup_loop():
        while True:
            time.sleep(interval_minutes * 60)
            create_backup()
            
    thread = threading.Thread(target=_backup_loop, daemon=True)
    thread.start()
