import customtkinter as ctk
import database
import barcode_logic
from ui import PharmacyApp

def main():
    # Set the general appearance of the custom tkinter window
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    # Initialize the database (creates tables if missing)
    database.init_db()
    
    # Ensure the labels directory exists
    barcode_logic.init_labels_dir()
    
    # Create and run the application
    app = PharmacyApp()
    app.mainloop()

if __name__ == "__main__":
    main()
