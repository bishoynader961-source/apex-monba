import re

schema_path = r'E:\my progam pharmacy\backend_fastapi\app\shared\schemas.py'
with open(schema_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(
    r'(primary_care_physician: Optional\[str\] = None\n    created_at: Optional\[ISOTime\] = None\n    is_deleted: bool = False)',
    r'\1\n    custom_fields: Optional[str] = None',
    text
)

text = re.sub(
    r'(last_fill_date: Optional\[str\] = None\n    prescriber_id: Optional\[int\] = None\n    primary_care_physician: Optional\[str\] = None)',
    r'\1\n    custom_fields: Optional[str] = None',
    text
)

with open(schema_path, 'w', encoding='utf-8') as f:
    f.write(text)

models_path = r'E:\my progam pharmacy\backend_fastapi\app\core\models.py'
with open(models_path, 'r', encoding='utf-8') as f:
    text2 = f.read()

text2 = re.sub(
    r'(zip: Mapped\[Optional\[str\]\] = mapped_column\(String, nullable=True\)\n    primary_care_physician: Mapped\[Optional\[str\]\] = mapped_column\(String, nullable=True\))',
    r'\1\n    custom_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)',
    text2
)

with open(models_path, 'w', encoding='utf-8') as f:
    f.write(text2)
