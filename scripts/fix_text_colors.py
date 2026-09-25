import os
import re

folder = 'e:\\my progam pharmacy\\app'
components_folder = 'e:\\my progam pharmacy\\components'
files_to_check = []

for fld in [folder, components_folder]:
    for root, dirs, files in os.walk(fld):
        for file in files:
            if file.endswith('.tsx') or file.endswith('.ts'):
                files_to_check.append(os.path.join(root, file))

def replacer(match):
    full_class_string = match.group(0)
    
    # If the class string contains a background color like bg-blue-600, bg-gray-800, skip it
    if re.search(r'\bbg-(?:gray|slate|blue|red|green|emerald|indigo|purple|amber|orange|cyan|sky|teal|violet|yellow)-(?:[5-9]00|950)\b', full_class_string):
        return full_class_string
        
    # Otherwise, replace light text classes with dual-mode classes
    # e.g., text-gray-200 -> text-gray-800 dark:text-gray-200
    new_class_string = full_class_string
    
    # We must ensure we only replace non-prefixed ones (e.g. not hover:text-gray-200 or dark:text-gray-200)
    # Using regex to find them inside the class string
    
    def token_repl(m):
        token = m.group(0)
        prefix = m.group(1) # any prefix like dark:, hover:, etc. If it exists, we skip if it's dark
        if prefix:
            return token
            
        color = m.group(2)
        shade = m.group(3)
        
        if color == 'white':
            return 'text-gray-900 dark:text-white'
        elif shade == '100' or shade == '200':
            return f'text-gray-800 dark:text-{color}-{shade}'
        elif shade == '300':
            return f'text-gray-700 dark:text-{color}-{shade}'
        elif shade == '400':
            return f'text-gray-600 dark:text-{color}-{shade}'
        return token

    # Tokenizer regex: matches optional prefix and the text utility
    new_class_string = re.sub(r'([a-z:-]+)?\btext-(gray|slate|white)(?:-([1-4]00))?\b', token_repl, new_class_string)
    
    return new_class_string

files_modified = 0

for path in files_to_check:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all className="..." or className={`...`} attributes
    new_content = re.sub(r'className=(?:\"[^\"]*\"|\'[^\']*\'|\{[`\'\"][^`\'\"]*[`\'\"]\})', replacer, content)
    
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        files_modified += 1

print(f"Modified {files_modified} files to add dark mode text color fallbacks.")
