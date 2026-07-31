import re


def _extract_first_var(text):
    m = re.search(r'\{\{(\w+)\}\}', text)
    return m.group(1) if m else None


def _extract_all_vars(text):
    return re.findall(r'\{\{(\w+)\}\}', text)


def apply_treeview_style(tree):
    """Applies the Design System styles and tags to a ttk.Treeview."""
    # Define row striping colors
    tree.tag_configure("odd", background="#2D2D2D", foreground="#FFFFFF")
    tree.tag_configure("even", background="#1E1E1E", foreground="#FFFFFF")
    
    # Status badges (for Inventory/Alerts)
    tree.tag_configure("status_green", background="#10B981", foreground="#FFFFFF")
    tree.tag_configure("status_yellow", background="#F59E0B", foreground="#FFFFFF")
    tree.tag_configure("status_red", background="#EF4444", foreground="#FFFFFF")

