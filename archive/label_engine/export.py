import json
import os
import sys
import logging
import tempfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_core import LabelCanvas, LabelElement, draw_elements

logger = logging.getLogger(__name__)

FILE_EXTENSION = ".json"
FILE_TYPES = [("Label Files", "*.json"), ("All Files", "*.*")]
PNG_FILE_TYPES = [("PNG Images", "*.png"), ("All Files", "*.*")]
DPI = 300
SCREEN_DPI = 96

LABELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "labels")
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "label_template.json")


def _ensure_labels_dir():
    os.makedirs(LABELS_DIR, exist_ok=True)


def get_label_path(product_id: str) -> str:
    _ensure_labels_dir()
    return os.path.join(LABELS_DIR, f"{product_id}.json")


def save_label_by_id(product_id: str, canvas: LabelCanvas) -> bool:
    return save_label(get_label_path(product_id), canvas)


def load_label_by_id(product_id: str, canvas: LabelCanvas) -> bool:
    path = get_label_path(product_id)
    if not os.path.exists(path):
        logger.info("No saved label for product %s, starting fresh", product_id)
        return False
    return load_label(path, canvas)


def save_label(filename: str, canvas: LabelCanvas) -> bool:
    try:
        data = {
            "canvas_width": canvas.width,
            "canvas_height": canvas.height,
            "elements": [elem.to_dict() for elem in canvas.elements],
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Label saved to %s (%d elements)", filename, len(canvas.elements))
        return True
    except Exception as e:
        logger.error("Save failed: %s", e)
        return False


def load_label(filename: str, canvas: LabelCanvas) -> bool:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        canvas.clear()
        canvas.set_size(data.get("canvas_width", 400), data.get("canvas_height", 300))
        for elem_data in data.get("elements", []):
            elem = LabelElement.from_dict(elem_data)
            canvas.elements.append(elem)
        canvas.redraw()
        logger.info("Label loaded from %s (%d elements)", filename, len(canvas.elements))
        return True
    except Exception as e:
        logger.error("Load failed: %s", e)
        return False


def export_to_png(filename: str, canvas: LabelCanvas) -> bool:
    try:
        scale = DPI / SCREEN_DPI
        img_w = int(canvas.width * scale)
        img_h = int(canvas.height * scale)
        img = Image.new("RGB", (img_w, img_h), "white")
        draw_elements(img, canvas.elements, scale=scale, context=canvas.var_context)
        img.save(filename, "PNG", dpi=(DPI, DPI))
        logger.info("PNG exported to %s (%dx%d @ %d DPI)", filename, img_w, img_h, DPI)
        return True
    except Exception as e:
        logger.error("PNG export failed: %s", e)
        return False


def print_label(canvas: LabelCanvas) -> bool:
    try:
        tmp_path = os.path.join(tempfile.gettempdir(), "label_print.png")
        if not export_to_png(tmp_path, canvas):
            return False
        os.startfile(tmp_path, "print")
        logger.info("Print command sent")
        return True
    except Exception as e:
        logger.error("Print failed: %s", e)
        return False


def save_template(canvas: LabelCanvas) -> bool:
    return save_label(TEMPLATE_PATH, canvas)


def load_template(canvas: LabelCanvas) -> bool:
    if not os.path.exists(TEMPLATE_PATH):
        return False
    return load_label(TEMPLATE_PATH, canvas)
