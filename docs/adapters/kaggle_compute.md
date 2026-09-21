# Adapter: KaggleComputeAdapter

**Purpose**: Implements `ComputeExecutionPort` using `kaggle` CLI.

**Responsibilities**:
- Patch `kernel-metadata.json` and `.ipynb` metadata.
- Handle account rotation.
- Classify Kaggle CLI status outputs robustly.
- Manage dataset/kernel lifecycle (push/pull).
- Canonical artifact retrieval: Defensively filters downloads to return only the canonical `_with_audio.mp4` file, falling back to plain `.mp4` if audio is missing. Supports `debug=True` to retrieve the full raw tree.
