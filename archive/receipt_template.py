import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipt_templates")
DEFAULT_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "default.json")


@dataclass
class ReceiptSection:
    """Represents a single section in a receipt template."""
    type: str  # "header", "separator", "text", "items_header", "items", "total", "footer"
    content: str = ""
    align: str = "left"  # "left", "center", "right"
    font_bold: bool = False
    char: str = "="  # for separator type


@dataclass
class ReceiptTemplate:
    """Represents a complete receipt template."""
    name: str = "Default"
    paper_width: int = 42
    is_default: bool = True
    sections: List[ReceiptSection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "paper_width": self.paper_width,
            "is_default": self.is_default,
            "sections": [
                {
                    "type": s.type,
                    "content": s.content,
                    "align": s.align,
                    "font_bold": s.font_bold,
                    "char": s.char,
                }
                for s in self.sections
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReceiptTemplate":
        sections = []
        for s in data.get("sections", []):
            sections.append(ReceiptSection(
                type=s.get("type", "text"),
                content=s.get("content", ""),
                align=s.get("align", "left"),
                font_bold=s.get("font_bold", False),
                char=s.get("char", "="),
            ))
        return cls(
            name=data.get("name", "Default"),
            paper_width=data.get("paper_width", 42),
            is_default=data.get("is_default", False),
            sections=sections,
        )


def get_default_template() -> ReceiptTemplate:
    """Returns the default receipt template."""
    return ReceiptTemplate(
        name="Default",
        paper_width=42,
        is_default=True,
        sections=[
            ReceiptSection(type="separator", char="="),
            ReceiptSection(type="header", content="{{pharmacy_name}}", align="center", font_bold=True),
            ReceiptSection(type="separator", char="="),
            ReceiptSection(type="text", content="Receipt #: {{receipt_id}}"),
            ReceiptSection(type="text", content="Date: {{date}}"),
            ReceiptSection(type="text", content="Payment: {{payment_method}}"),
            ReceiptSection(type="separator", char="-"),
            ReceiptSection(type="items_header", content="Product  Qty  Price  Total"),
            ReceiptSection(type="items", content="{{name:<16}}{{qty:>4}} {{price:>7.2f}} {{total:>8.2f}}"),
            ReceiptSection(type="separator", char="-"),
            ReceiptSection(type="total", content="TOTAL: {{grand_total}}"),
            ReceiptSection(type="text", content="Thank you!", align="center"),
            ReceiptSection(type="separator", char="="),
        ],
    )


def save_template(template: ReceiptTemplate, filepath: str = None) -> bool:
    """Saves a receipt template to a JSON file."""
    if filepath is None:
        filepath = DEFAULT_TEMPLATE_PATH
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(template.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ReceiptTemplate] Save failed: {e}")
        return False


def load_template(filepath: str = None) -> Optional[ReceiptTemplate]:
    """Loads a receipt template from a JSON file."""
    if filepath is None:
        filepath = DEFAULT_TEMPLATE_PATH
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ReceiptTemplate.from_dict(data)
    except Exception as e:
        print(f"[ReceiptTemplate] Load failed: {e}")
        return None


def ensure_default_template():
    """Creates the default template if it doesn't exist."""
    if not os.path.exists(DEFAULT_TEMPLATE_PATH):
        template = get_default_template()
        save_template(template)


def render_receipt(template: ReceiptTemplate, context: dict) -> str:
    """Renders a receipt template with the given context variables.

    Args:
        template: The receipt template to render
        context: Dictionary of variables to substitute (e.g., {"pharmacy_name": "My Pharmacy"})

    Returns:
        Formatted receipt string ready for ESC/POS printing
    """
    lines = []
    W = template.paper_width

    for section in template.sections:
        if section.type == "separator":
            line = section.char * W
            lines.append(line)

        elif section.type == "header":
            text = _resolve_variables(section.content, context)
            line = _format_line(text, W, section.align, section.font_bold)
            lines.append(line)

        elif section.type == "text":
            text = _resolve_variables(section.content, context)
            line = _format_line(text, W, section.align, section.font_bold)
            lines.append(line)

        elif section.type == "items_header":
            text = section.content if section.content else "Product  Qty  Price  Total"
            line = _format_line(text, W, "left", True)
            lines.append(line)

        elif section.type == "items":
            items = context.get("items", [])
            for item in items:
                line = _format_item_line(section.content, item, W)
                lines.append(line)

        elif section.type == "total":
            text = _resolve_variables(section.content, context)
            line = _format_line(text, W, "right", True)
            lines.append(line)

        elif section.type == "footer":
            text = _resolve_variables(section.content, context)
            line = _format_line(text, W, section.align, section.font_bold)
            lines.append(line)

    return "\n".join(lines)


def _resolve_variables(text: str, context: dict) -> str:
    """Replaces {{variable}} placeholders with values from context."""
    if not context:
        return text
    for key, val in context.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def _format_line(text: str, width: int, align: str = "left", bold: bool = False) -> str:
    """Formats a line with alignment and optional bold marker."""
    if len(text) > width:
        text = text[:width - 2] + ".."

    if align == "center":
        return text.center(width)
    elif align == "right":
        return text.rjust(width)
    else:
        return text.ljust(width)


def _format_item_line(template: str, item: dict, width: int) -> str:
    """Formats an item line using the template pattern."""
    try:
        name = str(item.get("name", ""))[:16]
        qty = item.get("qty", item.get("quantity", 0))
        price = item.get("price", 0)
        total = qty * price

        if len(name) > 16:
            name = name[:14] + ".."

        line = f"  {name:<16}{qty:>4} {price:>7.2f} {total:>8.2f}"
        if len(line) > width:
            line = line[:width]
        return line
    except (KeyError, TypeError, ValueError):
        return f"  {str(item)[:width - 2]}"


def get_receipt_context(receipt_id, receipt_data, items, pharmacy_name):
    """Builds the context dictionary for receipt rendering.

    Args:
        receipt_id: The receipt number
        receipt_data: Tuple from database.get_receipts() -> (id, timestamp, total, method)
        items: List of item tuples from database.get_receipt_items()
        pharmacy_name: Pharmacy name from config

    Returns:
        Context dictionary for render_receipt()
    """
    timestamp = receipt_data[1] if receipt_data else ""
    total = receipt_data[2] if receipt_data else 0
    method = receipt_data[3] if receipt_data else ""

    item_list = []
    for item in items:
        # item = (id, receipt_id, product_name, qty, price, barcode, vendor, expiry)
        item_list.append({
            "name": item[2] if len(item) > 2 else "",
            "qty": item[3] if len(item) > 3 else 0,
            "price": item[4] if len(item) > 4 else 0,
        })

    return {
        "pharmacy_name": pharmacy_name,
        "receipt_id": receipt_id,
        "date": timestamp,
        "payment_method": method,
        "grand_total": self.app.currency.fmt(total),
        "items": item_list,
    }
