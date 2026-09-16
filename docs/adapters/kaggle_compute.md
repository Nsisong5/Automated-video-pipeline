# Adapter: KaggleComputeAdapter

**Purpose**: Implements `ComputeExecutionPort` using `kaggle` CLI.

**Responsibilities**:
- Patch `kernel-metadata.json` and `.ipynb` metadata.
- Handle account rotation.
- Classify Kaggle CLI status outputs robustly.
- Manage dataset/kernel lifecycle (push/pull).
