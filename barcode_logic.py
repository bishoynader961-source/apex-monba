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
    PADDING = 30
    dummy_img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    name_bbox = draw.textbbox((0, 0), pharmacy_name, font=ImageFont.truetype("arial.ttf", int(font_size)))
    price_bbox = draw.textbbox((0, 0), f"${price:.2f}", font=ImageFont.truetype("arial.ttf", 16))
    expiry_text = "Exp: --/--"
    expiry_bbox = draw.textbbox((0, 0), expiry_text, font=ImageFont.truetype("arial.ttf", 16))
    
    name_height = name_bbox[3] - name_bbox[1]
    price_height = price_bbox[3] - price_bbox[1]
    expiry_height = expiry_bbox[3] - expiry_bbox[1]
    
    max_text_width = max(name_bbox[2] - name_bbox[0], price_bbox[2] - price_bbox[0], expiry_bbox[2] - expiry_bbox[0])
    total_text_height = name_height + price_height + expiry_height + 20  # 10px spacing between lines
    
    label_width = PADDING + max_text_width + PADDING + barcode_img.width + PADDING
    label_height = max(total_text_height, barcode_img.height) + PADDING * 2
    
    label_img = Image.new('RGB', (label_width, label_height), 'white')
    draw = ImageDraw.Draw(label_img)
    
    # Draw Pharmacy Name (centered at top)
    name_y = PADDING
    draw.text((PADDING, name_y), pharmacy_name, fill='black', font=ImageFont.truetype("arial.ttf", int(font_size)))
    name_y += name_height + 10
    
    # Draw Price if enabled
    if include_price:
        price_str = f"${price:.2f}"
        draw.text((PADDING, name_y), price_str, fill='black', font=ImageFont.truetype("arial.ttf", 16))
        name_y += price_height + 10
    
    # Draw Expiry Date
    expiry_text = "Exp: --/--"
    draw.text((PADDING, name_y), expiry_text, fill='black', font=ImageFont.truetype("arial.ttf", 16))
    
    # Center barcode vertically with 15px quiet zone padding
    barcode_x = PADDING + max_text_width + PADDING + 15
    barcode_y = (label_height - barcode_img.height) // 2
    label_img.paste(barcode_img, (barcode_x, barcode_y))
    
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
