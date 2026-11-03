# === HEADLESS "Step 4" — for backend-automated runs only ===
# Run Steps 1, 2, 3, 3.5 from your original notebook FIRST, unchanged.
# This REPLACES the original Step 4 for the automated flow. Keep your
# original Step 4 file separately for manual/interactive Gradio use.

import os
import sys
import json
import time
import subprocess
import logging
from gradio_client import Client, handle_file

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("notebook_orchestrator")

JOB_DATASET_SLUG = "ltx-job-request"

# --- Fetch the job queue the backend pushed before starting this notebook ---
import kaggle  # importing forces kaggle to read its configured credentials
OWNER_USERNAME = kaggle.api.get_config_value("username")

job_dataset_id = f"{OWNER_USERNAME}/{JOB_DATASET_SLUG}"
job_dir = "job_request"
os.makedirs(job_dir, exist_ok=True)
logger.info(f"Downloading job dataset from {job_dataset_id} to {job_dir}")
subprocess.run(["kaggle", "datasets", "download", "-d", job_dataset_id,
                "-p", job_dir, "--unzip", "--force"], check=True)

with open(os.path.join(job_dir, "jobs.json")) as f:
    jobs = json.load(f)["jobs"]

logger.info(f"Loaded {len(jobs)} job(s) from {job_dataset_id}")
for i, job in enumerate(jobs):
    logger.info(f"  job {i}: {job.get('prompt', '')[:60]}...")

# --- Launch the Gradio app ---
env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

app_process = subprocess.Popen(
    [sys.executable, "-u", "run_aiquest_ltx25_headless.py"],
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
)

ready = False
for line in app_process.stdout:
    print(line, end="")
    sys.stdout.flush()
    if "Running on local URL" in line:
        ready = True
        break

if not ready:
    raise RuntimeError("App process ended before the local server came up.")

time.sleep(5) 

client = Client("http://127.0.0.1:7860")

# --- Process Jobs ---
for i, job in enumerate(jobs):
    logger.info(f"\n=== Generating job {i+1}/{len(jobs)} ===")
    
    # Handle start_frame if provided by the backend
    start_frame_path = None
    if job.get("start_frame_filename"):
        potential_path = os.path.join(job_dir, job["start_frame_filename"])
        if os.path.exists(potential_path):
            start_frame_path = handle_file(potential_path)
            logger.info(f"  \u2705 Applying start frame: {job['start_frame_filename']}")
        else:
            logger.warning(f"  \u274c Start frame requested but not found: {potential_path}")

    logger.info(f"Submitting job {i+1} to Gradio client...")
    result = client.predict(
        prompt=job["prompt"],
        input_image_start=start_frame_path,
        input_image_end=None,
        seed=job.get("seed", -1),
        duration_dropdown=job.get("duration", "2 Seconds (49 frames - Fast)"),
        resolution_dropdown=job.get("resolution", "Fast Preview (384p - ~1-2 min)"),
        aspect_ratio_dropdown=job.get("aspect_ratio", "16:9 Landscape"),
        guide_scale=job.get("guide_scale", 1.0),
        audio_cfg=job.get("audio_cfg", 1.0),
        num_steps=job.get("num_steps", 8),
        api_name="/Video_Generation",
    )
    video_info, status_text = result
    logger.info(f"Job {i+1} status: {status_text}")

logger.info("\nAll jobs complete.")

# --- Cleanup ---
import glob
import json
import shutil

FINAL_OUTPUT_DIR = "/kaggle/working/final_output"
os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

# ... (Cleanup logic remains the same as your cin.md)
# (Truncated for brevity in tool output, but ensure your file has the rest of the cleanup code)
