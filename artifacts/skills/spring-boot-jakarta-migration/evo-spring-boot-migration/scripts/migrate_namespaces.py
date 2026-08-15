"""Migrate javax.* to jakarta.* namespaces in Java source files."""
import os
import re

NAMESPACE_REPLACEMENTS = [
    ('javax.persistence', 'jakarta.persistence'),
    ('javax.validation', 'jakarta.validation'),
    ('javax.servlet', 'jakarta.servlet'),
    ('javax.annotation', 'jakarta.annotation'),
    ('javax.transaction', 'jakarta.transaction'),
]

def migrate_file_namespaces(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    original = content
    for old_ns, new_ns in NAMESPACE_REPLACEMENTS:
        content = content.replace(old_ns, new_ns)
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  Migrated namespaces in {filepath}")
        return True
    return False

def migrate_all_namespaces(source_root):
    count = 0
    for root, dirs, files in os.walk(source_root):
        for fname in files:
            if fname.endswith('.java'):
                fpath = os.path.join(root, fname)
                if migrate_file_namespaces(fpath):
                    count += 1
    print(f"Migrated namespaces in {count} files")
    return count

if __name__ == '__main__':
    import sys
    migrate_all_namespaces(sys.argv[1] if len(sys.argv) > 1 else '/workspace/src')
