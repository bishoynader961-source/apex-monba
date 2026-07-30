import sys
import os
import json
import random
import time
import uuid
import subprocess
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
from path_utils import get_resource_path

CONFIG_FILE = get_resource_path("config.json")
LABELS_DIR = get_resource_path("labels")


def _find_python_executable():
    """Detect the correct Python executable, preferring the project venv.

    When running from source, sys.executable may point to a system Python
    (e.g., MinGW) that lacks the project's installed packages.  We always
    check for a project venv first, then fall back to sys.executable.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))

    venv_candidates = [
        os.path.join(base_dir, "venv", "Scripts", "python.exe"),
        os.path.join(os.path.dirname(base_dir), "venv", "Scripts", "python.exe"),
        os.path.join(base_dir, ".venv", "Scripts", "python.exe"),
    ]
    for candidate in venv_candidates:
        if os.path.exists(candidate):
            return candidate

    # Frozen build: sys.executable is the .exe itself — search PATH for a real Python
    if getattr(sys, 'frozen', False):
        import shutil
        for name in ("python", "python3", "python.exe", "python3.exe"):
            found = shutil.which(name)
            if found:
                return found

    return sys.executable


# --- BRIDGE FUNCTION FOR M8 INTEGRATION ---
def open_label_engine(product_id, barcode_value, name="", price="", expiry="", manufacture="",
                      show_name=True, show_price=True, show_expiry=True, show_barcode_text=True):
    """Launches the Label Engine and catches any instant crashes."""
    engine_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_engine", "main.py")

    # 1. Verify the file actually exists where we think it does
    if not os.path.exists(engine_path):
        raise Exception(f"Cannot find the M8 engine! Looking for it here:\n{engine_path}")

    # 2. Detect the correct Python executable (venv first, then sys.executable)
    python_exe = _find_python_executable()

    # Safety check: make sure we didn't land on a frozen .exe that can't run scripts
    if getattr(sys, 'frozen', False) and python_exe == sys.executable:
        raise Exception(
            "Cannot launch the Label Designer from the compiled .exe because no "
            "Python interpreter was found on this system.\n\n"
            "Install Python 3.12+ and ensure it is on the system PATH, or run "
            "the application from the development environment instead."
        )

    # 3. Launch the process and capture stderr so we can surface errors
    cmd = [
        python_exe,
        engine_path,
        "--id", str(product_id),
        "--barcode", str(barcode_value),
        "--name", str(name),
        "--price", str(price),
        "--show-name", str(show_name),
        "--show-price", str(show_price),
        "--show-expiry", str(show_expiry),
        "--show-barcode-text", str(show_barcode_text),
    ]
    if expiry:
        cmd.extend(["--expiry", str(expiry)])
    if manufacture:
        cmd.extend(["--manufacture", str(manufacture)])

    try:
        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # Wait briefly to detect immediate crashes (GUI apps stay running)
        try:
            stdout, stderr = process.communicate(timeout=3)
            # If we get here, the process exited within 3 seconds
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else "Unknown error"
                raise Exception(
                    f"Label engine crashed (exit code {process.returncode}).\n\n"
                    f"Error:\n{error_msg}"
                )
        except subprocess.TimeoutExpired:
            # Process is still running after 3 seconds — GUI app launched successfully
            pass

    except Exception as e:
        raise Exception(f"Could not launch Label Designer:\n{str(e)}")

def init_labels_dir():
    if not os.path.exists(LABELS_DIR):
        os.makedirs(LABELS_DIR)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "pharmacy_name": "My Pharmacy",
            "address": "",
            "phone": "",
            "tax_rate": 0.0,
            "low_stock_threshold": 5,
            "font_size": 20,
            "include_price": True,
            "db_path": "pharmacy.db",
            "expiry_alarm_days": 50,
            "expiry_ignore_list": []
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    defaults = {
        "pharmacy_name": "My Pharmacy",
        "address": "",
        "phone": "",
        "tax_rate": 0.0,
        "low_stock_threshold": 5,
        "font_size": 20,
        "include_price": True,
        "db_path": "pharmacy.db",
        "expiry_alarm_days": 50,
        "expiry_ignore_list": []
    }
    changed = False
    for key, val in defaults.items():
        if key not in config:
            config[key] = val
            changed = True
    if changed:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    return config

def generate_internal_barcode(vendor_name: str) -> str:
    prefix = vendor_name.strip()[:3].upper() if vendor_name and vendor_name.strip() and vendor_name.strip() != 'N/A' else 'PRD'
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

def create_label(price: float, internal_barcode: str) -> str:
    init_labels_dir()
    config = load_config()
    pharmacy_name = config.get("pharmacy_name", "My Pharmacy")
    font_size = config.get("font_size", 20)
    include_price = config.get("include_price", True)
    
    code128 = barcode.get_barcode_class('code128')
    writer = ImageWriter()
    my_barcode = code128(internal_barcode, writer=writer)
    
    temp_path = os.path.join(LABELS_DIR, f"temp_{internal_barcode}")
    my_barcode.save(temp_path)
    
    barcode_img_path = f"{temp_path}.png"
    barcode_img = Image.open(barcode_img_path)
    
    # Text calculation
    dummy_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    name_bbox = draw.textbbox((0, 0), pharmacy_name, font=ImageFont.truetype("arial.ttf", int(font_size)))
    price_bbox = draw.textbbox((0, 0), f"${price:.2f}", font=ImageFont.truetype("arial.ttf", 16))
    expiry_bbox = draw.textbbox((0, 0), "Exp: --/--", font=ImageFont.truetype("arial.ttf", 16))
    
    max_text_width = max(name_bbox[2] - name_bbox[0], price_bbox[2] - price_bbox[0], expiry_bbox[2] - expiry_bbox[0])
    label_width = 90 + max_text_width + barcode_img.width
    label_height = max(100, barcode_img.height + 60)
    
    label_img = Image.new('RGB', (label_width, label_height), 'white')
    draw = ImageDraw.Draw(label_img)
    
    # Drawing logic...
    draw.text((30, 30), pharmacy_name, fill='black', font=ImageFont.truetype("arial.ttf", int(font_size)))
    if include_price:
        draw.text((30, 60), f"${price:.2f}", fill='black', font=ImageFont.truetype("arial.ttf", 16))
    draw.text((30, 90), "Exp: --/--", fill='black', font=ImageFont.truetype("arial.ttf", 16))
    
    label_img.paste(barcode_img, (max_text_width + 60, (label_height - barcode_img.height) // 2))
    
    final_path = os.path.join(LABELS_DIR, f"{internal_barcode}_label.png")
    label_img.save(final_path)
    barcode_img.close()
    if os.path.exists(barcode_img_path):
        os.remove(barcode_img_path)
    return final_path

# ... (generate_preview_image function remains same)

def generate_preview_image(flags: dict, overrides: dict, internal_barcode: str) -> Image.Image:
    """
    Generates a live preview PIL Image.
    flags: dict of booleans (show_name, show_price, show_expiry, show_barcode_text)
    overrides: dict of strings (name, price, expiry)
    """
    code128 = barcode.get_barcode_class('code128')
    writer = ImageWriter()
    
    # Set up quiet zone and font options
    write_text = flags.get("show_barcode_text", True)
    writer_options = {
        'quiet_zone': 15.0,
        'module_width': 0.3,
        'module_height': 15.0,
        'font_size': 12 if write_text else 0,
        'text_distance': 5.0,
        'write_text': write_text
    }
    
    my_barcode = code128(internal_barcode, writer=writer)
    barcode_img = my_barcode.render(writer_options)
    
    dummy_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    # Get text elements
    name_text = overrides.get("name", "Product Name")
    price_text = overrides.get("price", "$0.00")
    expiry_text = overrides.get("expiry", "Exp: --/--")
    
    # Calculate text bounding boxes
    name_bbox = draw.textbbox((0, 0), name_text, font=ImageFont.truetype("arial.ttf", 28))
    price_bbox = draw.textbbox((0, 0), price_text, font=ImageFont.truetype("arial.ttf", 22))
    expiry_bbox = draw.textbbox((0, 0), expiry_text, font=ImageFont.truetype("arial.ttf", 22))
    
    name_height = name_bbox[3] - name_bbox[1]
    price_height = price_bbox[3] - price_bbox[1]
    expiry_height = expiry_bbox[3] - expiry_bbox[1]
    
    # Determine max text width and total text height
    max_text_width = max(name_bbox[2] - name_bbox[0], price_bbox[2] - price_bbox[0], expiry_bbox[2] - expiry_bbox[0])
    total_text_height = name_height + price_height + expiry_height + 20  # 10px spacing between lines
    
    # Calculate dynamic label dimensions
    PADDING = 30
    label_width = max_text_width + 20 + barcode_img.width + 30  # 20px between text and barcode, 15px padding on each side of barcode
    label_height = max(total_text_height, barcode_img.height) + 40  # 20px padding top and bottom
    
    # Create new label image with dynamic dimensions
    label_img = Image.new('RGB', (label_width, label_height), 'white')
    draw = ImageDraw.Draw(label_img)
    
    # Center text vertically
    text_y = (label_height - total_text_height) // 2
    
    # Draw text elements
    if flags.get("show_name", True):
        draw.text((20, text_y), name_text, fill='black', font=ImageFont.truetype("arial.ttf", 28))
        text_y += name_height + 10
    if flags.get("show_price", True):
        draw.text((20, text_y), price_text, fill='black', font=ImageFont.truetype("arial.ttf", 22))
        text_y += price_height + 10
    if flags.get("show_expiry", True):
        draw.text((20, text_y), expiry_text, fill='black', font=ImageFont.truetype("arial.ttf", 22))
    
    # Center barcode vertically with 15px quiet zone padding
    barcode_x = max_text_width + 20 + 15  # 15px padding between text and barcode
    barcode_y = (label_height - barcode_img.height) // 2
    label_img.paste(barcode_img, (barcode_x, barcode_y))
    
    return label_img
