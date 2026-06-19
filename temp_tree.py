import os

def generate_tree(startpath, out_file):
    exclude_dirs = {'.venv', 'node_modules', '.git', '__pycache__', 'venv', 'env', '.pytest_cache', 'build', 'dist', 'test', '.next'}
    
    with open(out_file, 'w', encoding='utf-8') as f:
        for root, dirs, files in os.walk(startpath):
            dirs[:] = sorted([d for d in dirs if d not in exclude_dirs])
            level = root.replace(startpath, '').count(os.sep)
            
            indent = '│   ' * (level - 1) + '├── ' if level > 0 else ''
            folder_name = os.path.basename(root)
            if level == 0:
                folder_name = os.path.basename(startpath)
            
            f.write(f'{indent}{folder_name}/\n')
            
            subindent = '│   ' * level + '├── '
            for file in sorted(files):
                # skip env files like .env, .env.local etc. and .pyc files
                if not 'env' in file.lower() and not file.endswith('.pyc'):
                    f.write(f'{subindent}{file}\n')

generate_tree('c:/Users/LENOVO/Desktop/kyapture', 'c:/Users/LENOVO/Desktop/kyapture/directory_structure.txt')