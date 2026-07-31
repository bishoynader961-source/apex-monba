# Pharmacy Management & Label Suite

A comprehensive pharmacy software solution designed for inventory management, data storage, and custom barcode/label design.

## 🚀 Overview
This application serves as an all-in-one suite for pharmacy operations:
* **Data Store:** Manages inventory, sales records, and product data.
* **Label Design Engine:** A powerful, modular tool for creating, saving, and printing professional-grade pharmacy labels.

## 🛠️ Key Features
* **Inventory Management:** Full CRUD operations for your pharmacy database.
* **Dynamic Label Designer:**
    * Drag-and-drop canvas for labels.
    * Supports Text, Shapes, Code128 Barcodes, and QR Codes.
    * Export as 300 DPI PNG or Print directly to system printer.
* **File Persistence:** JSON-based templates for label designs.

## 📦 Tech Stack
| Component | Technology |
| :--- | :--- |
| **GUI Framework** | CustomTkinter |
| **Data/Database** | [Your Database Tech, e.g., SQLite] |
| **Imaging** | Pillow (PIL) |
| **Barcode/QR** | python-barcode & qrcode |

## 🚀 Getting Started

### Prerequisites
* Python 3.12+

### Installation
1. Clone or copy the project folder.
2. Create virtual environment: `python -m venv venv`
3. Activate: `.\venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`

### Running the App
* **Launch Main Suite:** `python main_app.py`
* **Launch Label Designer Only:** `python label_engine/main.py`

## 📁 Project Structure
* `main_app.py` — The core Pharmacy Management system.
* `label_engine/` — The Label Design module.
* `requirements.txt` — Project dependencies.

## 📄 License
This project is licensed under the MIT License. See the `LICENSE` file for details.