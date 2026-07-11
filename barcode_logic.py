import os
import json
import random
import time
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

LABELS_DIR = "labels"
CONFIG_FILE = "config.json"

def init_labels_dir():
    if not os.path.exists(LABELS_DIR):
        os.makedirs(LABELS_DIR)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "pharmacy_name": "My Pharmacy",
            "font_size": 20,
            "include_price": True,
            "db_path": "pharmacy.db"
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def generate_internal_barcode(mfg_barcode: str) -> str:
    """
    Generates a unique internal barcode by appending a short suffix
    to the manufacturer barcode. Suffix is based on current time.
    """
    # A 4-digit suffix from timestamp and random to ensure uniqueness
    suffix = str(int(time.time() * 1000) % 10000).zfill(4)
    # optionally add a random digit or two
    random_part = str(random.randint(10, 99))
    
    # Just in case mfg_barcode is empty
    base = mfg_barcode.strip() if mfg_barcode.strip() else "PROD"
    return f"{base}-{suffix}{random_part}"

def create_label(price: float, internal_barcode: str) -> str:
    """
    Generates a barcode image with the dynamic settings and price on it.
    Returns the file path of the generated label image.
    """
    init_labels_dir()
    config = load_config()
    
    pharmacy_name = config.get("pharmacy_name", "My Pharmacy")
    font_size = config.get("font_size", 20)
    include_price = config.get("include_price", True)
    
    # Generate barcode image in memory
    code128 = barcode.get_barcode_class('code128')
    # Use ImageWriter to generate an image rather than SVG
    writer = ImageWriter()
    # Generate the barcode
    my_barcode = code128(internal_barcode, writer=writer)
    
    temp_path = os.path.join(LABELS_DIR, f"temp_{internal_barcode}")
    my_barcode.save(temp_path) # saves as temp_path.png
    
    barcode_img_path = f"{temp_path}.png"
    barcode_img = Image.open(barcode_img_path)
    
    # Create a blank white canvas for the label
    label_width = max(350, barcode_img.width + 40)
    label_height = barcode_img.height + 80
    label_img = Image.new('RGB', (label_width, label_height), 'white')
    
    draw = ImageDraw.Draw(label_img)
    
    try:
        # Use arial if available, else default
        font_large = ImageFont.truetype("arial.ttf", int(font_size))
        font_medium = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
    
    # Draw Pharmacy Name (centered at top)
    name_bbox = draw.textbbox((0, 0), pharmacy_name, font=font_large)
    name_w = name_bbox[2] - name_bbox[0]
    draw.text(((label_width - name_w) / 2, 10), pharmacy_name, fill='black', font=font_large)
    
    # Draw Price if enabled
    if include_price:
        price_str = f"${price:.2f}"
        price_bbox = draw.textbbox((0, 0), price_str, font=font_medium)
        price_w = price_bbox[2] - price_bbox[0]
        draw.text(((label_width - price_w) / 2, 35), price_str, fill='black', font=font_medium)
    
    # Paste barcode
    paste_x = (label_width - barcode_img.width) // 2
    paste_y = 60
    label_img.paste(barcode_img, (paste_x, paste_y))
    
    # Save final label
    final_path = os.path.join(LABELS_DIR, f"{internal_barcode}_label.png")
    label_img.save(final_path)
    
    # Cleanup temp barcode file
    barcode_img.close()
    if os.path.exists(barcode_img_path):
        os.remove(barcode_img_path)
        
    return final_path

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
    
    try:
        font_large = ImageFont.truetype("arial.ttf", 28)
        font_medium = ImageFont.truetype("arial.ttf", 22)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        
    text_width = 300
    label_height = max(barcode_img.height + 40, 200)
    label_width = text_width + barcode_img.width + 40
    
    label_img = Image.new('RGB', (label_width, label_height), 'white')
    draw = ImageDraw.Draw(label_img)
    
    y_offset = (label_height - 120) // 2 # center the text roughly
    if y_offset < 20: y_offset = 20
    
    if flags.get("show_name", True):
        draw.text((20, y_offset), overrides.get("name", "Product Name"), fill='black', font=font_large)
        y_offset += 45
        
    if flags.get("show_price", True):
        draw.text((20, y_offset), overrides.get("price", "$0.00"), fill='black', font=font_medium)
        y_offset += 35
        
    if flags.get("show_expiry", True):
        draw.text((20, y_offset), overrides.get("expiry", "Exp: --/--"), fill='black', font=font_medium)
        
    # Paste barcode on the right
    paste_x = text_width + 20
    paste_y = (label_height - barcode_img.height) // 2
    label_img.paste(barcode_img, (paste_x, paste_y))
    
    return label_img
