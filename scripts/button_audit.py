import os
import re

button_pattern = re.compile(r'<([bB]utton)([^>]*?)>', re.DOTALL)

found = []

for folder in ['app', 'components']:
    folder_path = os.path.join('e:\\my progam pharmacy', folder)
    if not os.path.exists(folder_path): continue
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                matches = button_pattern.finditer(content)
                for match in matches:
                    tag_name = match.group(1)
                    attrs = match.group(2)
                    
                    start_pos = match.start()
                    line_num = content[:start_pos].count('\n') + 1
                    
                    has_onclick = 'onClick=' in attrs or 'onClick {' in attrs or 'onClick{' in attrs
                    has_lowercase_onclick = 'onclick=' in attrs
                    is_submit = 'type="submit"' in attrs or "type='submit'" in attrs
                    
                    if has_lowercase_onclick and not has_onclick:
                        found.append(f"Lowercase onclick (Line {line_num}): {filepath} -> <{tag_name} {attrs.strip()}>")
                    elif not has_onclick and not is_submit:
                        found.append(f"No onClick (Line {line_num}): {filepath} -> <{tag_name} {attrs.strip()[:60]}...>")
                    elif has_onclick:
                        onclick_match = re.search(r'onClick=\{([^}]+)\}', attrs)
                        if onclick_match:
                            handler = onclick_match.group(1).strip()
                            handler_nospace = handler.replace(' ', '')
                            if handler_nospace in ('()=>{}', 'undefined', 'null'):
                                found.append(f"Empty onClick (Line {line_num}): {filepath} -> {handler}")
                            if 'console.log' in handler:
                                found.append(f"Console.log onClick (Line {line_num}): {filepath} -> {handler}")
                            if 'coming soon' in handler.lower():
                                found.append(f"Coming soon onClick (Line {line_num}): {filepath} -> {handler}")
                                
for f in found:
    print(f)
