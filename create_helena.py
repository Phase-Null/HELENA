import json
import os
from pathlib import Path

# Load the JSON
with open('helena_files.json', 'r', encoding='utf-8') as f:
    files = json.load(f)

# Create each file
for filepath, content in files.items():
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Created: {filepath}")

print("\nAll HELENA files created successfully!")