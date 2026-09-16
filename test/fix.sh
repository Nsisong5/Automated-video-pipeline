python3 -c "
import json

notebook_file = 'ltx-video.ipynb'

with open(notebook_file, 'r') as f:
    nb = json.load(f)

# Completely delete the Kaggle UI embedded settings if they exist
if 'metadata' in nb and 'kaggle' in nb['metadata']:
    del nb['metadata']['kaggle']

with open(notebook_file, 'w') as f:
    json.dump(nb, f, indent=2)
print('Conflicting Kaggle metadata stripped successfully!')
"
