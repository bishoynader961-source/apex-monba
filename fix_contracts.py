import re

contracts_path = r'E:\my progam pharmacy\types\contracts.ts'
with open(contracts_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(
    r'(primary_care_physician\?: string \| null;)',
    r'\1\n  custom_fields?: string | null;',
    text
)

with open(contracts_path, 'w', encoding='utf-8') as f:
    f.write(text)
