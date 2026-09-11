# Project: Automated LTX-Video Generation on Kaggle

## Overview
This project provides an automated pipeline for generating video clips using the [LTX-Video model](https://huggingface.co/Lightricks/LTX-Video) on the Kaggle platform. It allows users to offload compute-intensive video generation tasks to Kaggle notebooks, managing multiple Kaggle accounts to bypass resource or runtime limitations.

## Core Components

### 1. Backend Orchestrator (Client Machine)
The scripts in `/sdcard/LTX-VIDEO/` act as the control plane running on the user's local machine:
- **`run_backend_job_cycle.py`**: The entry point. Manages the end-to-end lifecycle:
  - Rotates Kaggle accounts via `kaggle_accounts.py`.
  - Pushes a job request dataset (via `kaggle_notebook_control.py`).
  - Triggers the Kaggle notebook to run (`kaggle_notebook_control.py`).
  - Polls for completion and downloads results.
  - Cleans up temporary artifacts.
- **`kaggle_accounts.py`**: Implements round-robin rotation of Kaggle credentials stored locally, ensuring the backend can distribute jobs across multiple accounts.
- **`kaggle_notebook_control.py`**: Interacts with the Kaggle API to push datasets, update notebook metadata, and manage the execution lifecycle.
- **`backend_ltx_client.py`**: Communicates with the Gradio interface running *inside* the active Kaggle notebook to trigger specific video generation tasks.

### 2. Kaggle-Side Execution (The Notebook)
- **`ltx-video.ipynb`**: The primary Jupyter notebook hosted on Kaggle. It is designed to be configured for dual-GPU environments (T4 x2) and contains the LTX-Video model logic.
- **`kaggle_headless_step4.py`**: A specialized script that runs within the Kaggle notebook environment. It:
  - Downloads the job request dataset created by the backend.
  - Launches the Gradio-based model app locally on the Kaggle machine (`127.0.0.1:7860`).
  - Uses the `gradio_client` library to interface with the local app, fulfilling the requested jobs.
  - Shuts down the local app and triggers notebook completion upon finishing.

## Typical Workflow

1.  **Job Definition**: The user defines a batch of generation tasks in `run_backend_job_cycle.py`.
2.  **Orchestration**: The local backend rotates to an available Kaggle account.
3.  **Job Submission**: The backend pushes a `jobs.json` to a Kaggle dataset (`<username>/ltx-job-request`).
4.  **Notebook Execution**: The backend triggers the Kaggle notebook (`<username>/ltx-video`).
5.  **In-Notebook Processing**: The notebook runs `kaggle_headless_step4.py`, which reads the job queue, runs the model via a local Gradio client, and saves results.
6.  **Retrieval**: The backend detects completion, downloads the generated video clips, and deletes the job request dataset.
