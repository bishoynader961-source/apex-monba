import io
import math
import uuid
import logging
import tkinter as tk
from dataclasses import dataclass, field

import barcode
from barcode.writer import ImageWriter
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageTk

logger = logging.getLogger(__name__)

CANVAS_BG = "#2b2b2b"
SELECTED_OUTLINE = "#3484F0"
RESIZE_HANDLE = 6

_DEFAULT_CONTEXT = {}


def resolve_variables(text: str, context: dict = None) -> str:
    if not context:
        context = _DEFAULT_CONTEXT
    for key, val in context.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


@dataclass
class LabelElement:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    type: str = "text"
    x: int = 50
    y: int = 50
    width: int = 120
    height: int = 40
    props: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "props": dict(self.props),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LabelElement":
        t = data.get("type", "text")
        if t == "barcode":
            return BarcodeElement(**{k: data[k] for k in ("id", "x", "y", "width", "height", "props") if k in data})
        if t == "qr":
            return QRElement(**{k: data[k] for k in ("id", "x", "y", "width", "height", "props") if k in data})
        if t == "shape":
            return ShapeElement(**{k: data[k] for k in ("id", "x", "y", "width", "height", "props") if k in data})
        return cls(
            id=data["id"],
            type=data["type"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            props=dict(data.get("props", {})),
        )


class BarcodeElement(LabelElement):
    def __init__(self, **kwargs):
        kwargs.setdefault("type", "barcode")
        kwargs.setdefault("width", 200)
        kwargs.setdefault("height", 80)
        kwargs.setdefault("props", {})
        props = kwargs["props"]
        props.setdefault("data", "SAMPLE-12345")
        props.setdefault("barcode_type", "code128")
        props.setdefault("show_text", True)
        super().__init__(**kwargs)


class QRElement(LabelElement):
    def __init__(self, **kwargs):
        kwargs.setdefault("type", "qr")
        kwargs.setdefault("width", 120)
        kwargs.setdefault("height", 120)
        kwargs.setdefault("props", {})
        props = kwargs["props"]
        props.setdefault("data", "https://example.com")
        props.setdefault("fill_color", "#000000")
        props.setdefault("back_color", "#ffffff")
        super().__init__(**kwargs)


class ShapeElement(LabelElement):
    def __init__(self, **kwargs):
        kwargs.setdefault("type", "shape")
        kwargs.setdefault("width", 120)
        kwargs.setdefault("height", 120)
        kwargs.setdefault("props", {})
        props = kwargs["props"]
        props.setdefault("shape", "rectangle")
        props.setdefault("fill_color", "#cccccc")
        props.setdefault("border_color", "#000000")
        props.setdefault("border_width", 2)
        super().__init__(**kwargs)


MIN_FONT_SIZE = 8
TEXT_LEFT_MARGIN = 15
RIGHT_PADDING = 20


def _fit_text_to_width(text, font_family, font_size, max_width, scale=1.0):
    fitted_size = max(MIN_FONT_SIZE, int(font_size * scale))
    try:
        font = ImageFont.truetype(f"{font_family}.ttf", fitted_size)
    except OSError:
        try:
            font = ImageFont.truetype(f"{font_family}.TTF", fitted_size)
        except OSError:
            try:
                font = ImageFont.truetype("arial.ttf", fitted_size)
            except OSError:
                font = ImageFont.load_default()

    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]

    while tw > max_width and fitted_size > MIN_FONT_SIZE:
        fitted_size -= 1
        try:
            font = ImageFont.truetype(f"{font_family}.ttf", fitted_size)
        except OSError:
            try:
                font = ImageFont.truetype(f"{font_family}.TTF", fitted_size)
            except OSError:
                try:
                    font = ImageFont.truetype("arial.ttf", fitted_size)
                except OSError:
                    font = ImageFont.load_default()
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]

    use_wrap = False
    if tw > max_width and " " in text:
        use_wrap = True

    return text, fitted_size, use_wrap


def _rounded_rect_coords(x0, y0, x1, y1, r):
    points = []
    steps = 12
    for i in range(steps + 1):
        angle = math.pi / 2 + (math.pi / 2) * i / steps
        points.append((x0 + r + r * math.cos(angle), y0 + r + r * math.sin(angle)))
    for i in range(steps + 1):
        angle = (math.pi / 2) * i / steps
        points.append((x1 - r + r * math.cos(angle), y0 + r + r * math.sin(angle)))
    for i in range(steps + 1):
        angle = -math.pi / 2 + (math.pi / 2) * i / steps
        points.append((x1 - r + r * math.cos(angle), y1 - r + r * math.sin(angle)))
    for i in range(steps + 1):
        angle = (math.pi / 2) * i / steps
        points.append((x0 + r + r * math.cos(angle), y1 - r + r * math.sin(angle)))
    return points


def _get_font(elem, scale=1.0):
    font_family = elem.props.get("font", "Arial")
    font_size = max(8, int(elem.props.get("font_size", 16) * scale))
    try:
        return ImageFont.truetype(f"{font_family}.ttf", font_size)
    except OSError:
        try:
            return ImageFont.truetype(f"{font_family}.TTF", font_size)
        except OSError:
            try:
                return ImageFont.truetype("arial.ttf", font_size)
            except OSError:
                return ImageFont.load_default()


def _generate_barcode_img(elem):
    data = elem.props.get("data", "")
    if not data:
        return None
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    show_text = elem.props.get("show_text", True)
    options = {"write_text": show_text, "module_width": 0.3, "module_height": 10.0, "quiet_zone": 2.0}
    bc = code128(data, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _generate_qr_img(elem):
    data = elem.props.get("data", "")
    if not data:
        return None
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    fill = elem.props.get("fill_color", "#000000")
    back = elem.props.get("back_color", "#ffffff")
    return qr.make_image(fill_color=fill, back_color=back).convert("RGB")


def draw_elements(surface, elements, scale=1.0, context=None):
    is_pil = isinstance(surface, Image.Image)
    is_tk = isinstance(surface, tk.Canvas)

    for elem in elements:
        x0, y0 = elem.x * scale + TEXT_LEFT_MARGIN * scale, elem.y * scale
        w, h = elem.width * scale, elem.height * scale
        x1, y1 = x0 + w, y0 + h
        fill_color = elem.props.get("fill_color", elem.props.get("fill", "#cccccc"))
        border_color = elem.props.get("border_color", elem.props.get("outline", "#000000"))
        bw = int(elem.props.get("border_width", 2) * scale)

        if elem.type == "text":
            text = resolve_variables(elem.props.get("text", "Text"), context)
            color = elem.props.get("color", "#000000")
            font_family = elem.props.get("font", "Arial")
            font_size = elem.props.get("font_size", 16)
            max_width = max(40, w - RIGHT_PADDING * scale)
            _, fitted_size, use_wrap = _fit_text_to_width(text, font_family, font_size, max_width, scale)
            if is_tk:
                wrap_width = w if use_wrap or elem.props.get("wrap") else 0
                surface.create_text(
                    x0, y0 + h // 2,
                    text=text, font=(font_family, fitted_size),
                    fill=color, width=wrap_width, anchor="w",
                )
            elif is_pil:
                try:
                    font = ImageFont.truetype(f"{font_family}.ttf", fitted_size)
                except OSError:
                    try:
                        font = ImageFont.truetype(f"{font_family}.TTF", fitted_size)
                    except OSError:
                        try:
                            font = ImageFont.truetype("arial.ttf", fitted_size)
                        except OSError:
                            font = ImageFont.load_default()
                draw = ImageDraw.Draw(surface)
                if use_wrap:
                    lines = []
                    words = text.split()
                    current = ""
                    for word in words:
                        test = f"{current} {word}".strip()
                        bbox = font.getbbox(test)
                        if bbox[2] - bbox[0] > w and current:
                            lines.append(current)
                            current = word
                        else:
                            current = test
                    if current:
                        lines.append(current)
                    y_line = y0
                    for line in lines:
                        draw.text((x0, y_line), line, fill=color, font=font)
                        y_line += (font.getbbox(line)[3] - font.getbbox(line)[1]) + 2
                else:
                    draw.text((x0, y0 + (h - draw.textbbox((0, 0), text, font=font)[3]) / 2), text, fill=color, font=font)

        elif elem.type == "shape":
            shape = elem.props.get("shape", "rectangle")
            if shape == "ellipse":
                if is_tk:
                    surface.create_oval(x0, y0, x1, y1, fill=fill_color, outline=border_color, width=bw)
                elif is_pil:
                    draw = ImageDraw.Draw(surface)
                    draw.ellipse([x0, y0, x1, y1], fill=fill_color, outline=border_color, width=bw)
            elif shape == "rounded-rectangle":
                r = min(20 * scale, w / 4, h / 4)
                pts = _rounded_rect_coords(x0, y0, x1, y1, r)
                if is_tk:
                    flat = [c for p in pts for c in p]
                    surface.create_polygon(flat, fill=fill_color, outline=border_color, width=bw, smooth=False)
                elif is_pil:
                    draw = ImageDraw.Draw(surface)
                    draw.polygon(pts, fill=fill_color, outline=border_color)
            else:
                if is_tk:
                    surface.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline=border_color, width=bw)
                elif is_pil:
                    draw = ImageDraw.Draw(surface)
                    draw.rectangle([x0, y0, x1, y1], fill=fill_color, outline=border_color, width=bw)

        elif elem.type == "barcode":
            bc_data = resolve_variables(elem.props.get("data", ""), context)
            if is_tk:
                try:
                    resolved_elem = BarcodeElement(
                        id=elem.id, x=elem.x, y=elem.y,
                        width=elem.width, height=elem.height,
                        props={**elem.props, "data": bc_data},
                    )
                    img = _generate_barcode_img(resolved_elem)
                    img = img.resize((int(w), int(h)), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    surface._image_cache = getattr(surface, "_image_cache", {})
                    surface._image_cache[elem.id] = tk_img
                    surface.create_image(x0, y0, anchor="nw", image=tk_img)
                except Exception as e:
                    surface.create_text(
                        x0 + w // 2, y0 + h // 2,
                        text=f"[Barcode Error: {e}]", fill="red", font=("Arial", max(8, int(9 * scale))),
                    )
            elif is_pil:
                try:
                    resolved_elem = BarcodeElement(
                        id=elem.id, x=elem.x, y=elem.y,
                        width=elem.width, height=elem.height,
                        props={**elem.props, "data": bc_data},
                    )
                    img = _generate_barcode_img(resolved_elem)
                    img = img.resize((int(w), int(h)), Image.LANCZOS)
                    surface.paste(img, (int(x0), int(y0)))
                except Exception:
                    draw = ImageDraw.Draw(surface)
                    draw.text((x0, y0), "[Barcode Error]", fill="red")

        elif elem.type == "qr":
            if is_tk:
                try:
                    img = _generate_qr_img(elem)
                    img = img.resize((int(w), int(h)), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    surface._image_cache = getattr(surface, "_image_cache", {})
                    surface._image_cache[elem.id] = tk_img
                    surface.create_image(x0, y0, anchor="nw", image=tk_img)
                except Exception as e:
                    surface.create_text(
                        x0 + w // 2, y0 + h // 2,
                        text=f"[QR Error: {e}]", fill="red", font=("Arial", max(8, int(9 * scale))),
                    )
            elif is_pil:
                try:
                    img = _generate_qr_img(elem)
                    img = img.resize((int(w), int(h)), Image.LANCZOS)
                    surface.paste(img, (int(x0), int(y0)))
                except Exception:
                    draw = ImageDraw.Draw(surface)
                    draw.text((x0, y0), "[QR Error]", fill="red")


class LabelCanvas:
    def __init__(self, parent, width: int = 400, height: int = 300):
        self.width = width
        self.height = height
        self.elements: list[LabelElement] = []
        self.selected_id: str | None = None
        self.on_select = None
        self._image_cache: dict[str, ImageTk.PhotoImage] = {}
        self._drag_data: dict | None = None
        self._resize_data: dict | None = None
        self.var_context: dict = {}

        self.frame = tk.Frame(parent, bg=CANVAS_BG)

        self.v_scroll = tk.Scrollbar(self.frame, orient="vertical")
        self.h_scroll = tk.Scrollbar(self.frame, orient="horizontal")

        self.canvas = tk.Canvas(
            self.frame,
            width=self.width,
            height=self.height,
            bg="white",
            highlightthickness=1,
            highlightbackground="#555",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self._update_scrollregion()

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        logger.info("LabelCanvas created (%dx%d)", self.width, self.height)

    def _update_scrollregion(self):
        self.canvas.config(scrollregion=(0, 0, self.width, self.height))

    def _canvas_coords(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def set_size(self, width: int, height: int):
        self.width = width
        self.height = height
        self.canvas.config(width=self.width, height=self.height)
        self._update_scrollregion()
        self.redraw()
        logger.info("Canvas resized to %dx%d", width, height)

    def add_element(self, element: LabelElement):
        self.elements.append(element)
        self.redraw()
        logger.info("Added element %s (type=%s)", element.id, element.type)

    def remove_element(self, element_id: str):
        self.elements = [e for e in self.elements if e.id != element_id]
        self._image_cache.pop(element_id, None)
        if self.selected_id == element_id:
            self.selected_id = None
        self.redraw()

    def get_element(self, element_id: str) -> LabelElement | None:
        for e in self.elements:
            if e.id == element_id:
                return e
        return None

    def select(self, element_id: str | None):
        self.selected_id = element_id
        self.redraw()
        if self.on_select:
            elem = self.get_element(element_id) if element_id else None
            self.on_select(elem)

    def clear(self):
        self.elements.clear()
        self._image_cache.clear()
        self.selected_id = None
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        draw_elements(self.canvas, self.elements, scale=1.0, context=self.var_context)
        self.canvas._image_cache = self._image_cache
        if self.selected_id:
            sel = self.get_element(self.selected_id)
            if sel:
                self.canvas.create_rectangle(
                    sel.x - 2, sel.y - 2,
                    sel.x + sel.width + 2, sel.y + sel.height + 2,
                    outline=SELECTED_OUTLINE, width=2, dash=(4, 4),
                )
                self._draw_resize_handles(sel)

    def _draw_resize_handles(self, elem: LabelElement):
        handles = self._get_handle_positions(elem)
        for hx, hy in handles:
            self.canvas.create_rectangle(
                hx - RESIZE_HANDLE // 2, hy - RESIZE_HANDLE // 2,
                hx + RESIZE_HANDLE // 2, hy + RESIZE_HANDLE // 2,
                fill=SELECTED_OUTLINE, outline="white", width=1,
                tags="handle",
            )

    def _get_handle_positions(self, elem: LabelElement):
        x0, y0 = elem.x, elem.y
        x1, y1 = elem.x + elem.width, elem.y + elem.height
        mx = (x0 + x1) // 2
        my = (y0 + y1) // 2
        return [(x1, y1), (x0, y1), (x1, y0), (mx, y1), (x1, my)]

    def _hit_handle(self, event) -> str | None:
        if not self.selected_id:
            return None
        sel = self.get_element(self.selected_id)
        if not sel:
            return None
        cx, cy = self._canvas_coords(event)
        positions = {
            "se": (sel.x + sel.width, sel.y + sel.height),
            "sw": (sel.x, sel.y + sel.height),
            "ne": (sel.x + sel.width, sel.y),
            "s": ((sel.x + sel.x + sel.width) // 2, sel.y + sel.height),
            "e": (sel.x + sel.width, (sel.y + sel.y + sel.height) // 2),
        }
        for name, (hx, hy) in positions.items():
            if abs(cx - hx) <= RESIZE_HANDLE and abs(cy - hy) <= RESIZE_HANDLE:
                return name
        return None

    def _on_press(self, event):
        cx, cy = self._canvas_coords(event)
        handle = self._hit_handle(event)
        if handle and self.selected_id:
            sel = self.get_element(self.selected_id)
            if sel:
                self._resize_data = {"handle": handle, "start_x": cx, "start_y": cy,
                                     "orig_x": sel.x, "orig_y": sel.y, "orig_w": sel.width, "orig_h": sel.height}
                return
        hit = None
        for elem in reversed(self.elements):
            if elem.x <= cx <= elem.x + elem.width and elem.y <= cy <= elem.y + elem.height:
                hit = elem.id
                break
        if hit:
            elem = self.get_element(hit)
            self._drag_data = {"id": hit, "start_x": cx - elem.x, "start_y": cy - elem.y}
            self.select(hit)
        else:
            self.select(None)

    def _on_drag(self, event):
        if self._resize_data:
            self._do_resize(event)
        elif self._drag_data:
            self._do_drag(event)

    def _on_release(self, event):
        self._drag_data = None
        self._resize_data = None

    def _do_drag(self, event):
        elem = self.get_element(self._drag_data["id"])
        if not elem:
            return
        cx, cy = self._canvas_coords(event)
        elem.x = max(0, min(cx - self._drag_data["start_x"], self.width - elem.width))
        elem.y = max(0, min(cy - self._drag_data["start_y"], self.height - elem.height))
        self.redraw()

    def _do_resize(self, event):
        sel = self.get_element(self.selected_id)
        if not sel:
            return
        cx, cy = self._canvas_coords(event)
        d = self._resize_data
        dx = cx - d["start_x"]
        dy = cy - d["start_y"]
        h = d["handle"]
        new_x, new_y = d["orig_x"], d["orig_y"]
        new_w, new_h = d["orig_w"], d["orig_h"]
        if "e" in h:
            new_w = max(30, d["orig_w"] + dx)
        if "s" in h:
            new_h = max(30, d["orig_h"] + dy)
        if h == "sw":
            new_x = d["orig_x"] + dx
            new_w = max(30, d["orig_w"] - dx)
        sel.x = max(0, new_x)
        sel.y = max(0, new_y)
        sel.width = int(new_w)
        sel.height = int(new_h)
        self.redraw()
