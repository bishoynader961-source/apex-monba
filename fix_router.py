import re
file_path = r'E:\my progam pharmacy\backend_fastapi\app\api\routers\label_template_route.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('@router.get("/")', '@router.get("")')
text = text.replace('@router.post("/")', '@router.post("")')
text = text.replace('product_router.get("/")', 'product_router.get("")')
text = text.replace('product_router.post("/")', 'product_router.post("")')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
