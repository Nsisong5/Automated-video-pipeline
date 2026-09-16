# === HEADLESS "Step 4" — for backend-automated runs only ===
# Run Steps 1, 2, 3, 3.5 from your original notebook FIRST, unchanged.
# This REPLACES the original Step 4 for the automated flow. Keep your
# original Step 4 file separately for manual/interactive Gradio use.

import os
import sys
import json
import time
import subprocess

JOB_DATASET_SLUG = "ltx-job-request"

# --- Fetch the job queue the backend pushed before starting this notebook ---
# The dataset owner is whichever Kaggle account this notebook run belongs to
# — Kaggle exposes that as KAGGLE_KERNEL_RUN_TYPE / the notebook's own
# metadata isn't directly available as an env var, so we read it from
# whatever KAGGLE_USERNAME was baked into this session's credentials.
import kaggle  # importing forces kaggle to read its configured credentials
OWNER_USERNAME = kaggle.api.get_config_value("username")

job_dataset_id = f"{OWNER_USERNAME}/{JOB_DATASET_SLUG}"
job_dir = "job_request"
os.makedirs(job_dir, exist_ok=True)
subprocess.run(["kaggle", "datasets", "download", "-d", job_dataset_id,
                "-p", job_dir, "--unzip", "--force"], check=True)

with open(os.path.join(job_dir, "jobs.json")) as f:
    jobs = json.load(f)["jobs"]

print(f"Loaded {len(jobs)} job(s) from {job_dataset_id}")
for i, job in enumerate(jobs):
    print(f"  job {i}: {job.get('prompt', '')[:60]}...")

# --- Launch the SAME app as before, but non-blocking and localhost-only —
# no public tunnel needed since we're calling it from inside this same
# notebook process. ---
env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

app_process = subprocess.Popen(
    [sys.executable, "-u", "run_aiquest_ltx25_headless.py"],
    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
)

# NOTE: run_aiquest_ltx25_headless.py is a copy of your existing
# run_aiquest_ltx25.py with ONE change at the very bottom:
#
#   demo.launch(
#       server_name="127.0.0.1", server_port=7860, share=False,
#       inline=False, debug=True, show_error=True, max_threads=4,
#       prevent_thread_lock=True,   # <-- the only real change: don't block
#   )
#
# prevent_thread_lock=True is what lets the code below actually run instead
# of hanging forever inside launch(). Copy Step 3's aiquest_app_code, change
# that one call, and write it to run_aiquest_ltx25_headless.py instead.

ready = False
for line in app_process.stdout:
    print(line, end="")
    sys.stdout.flush()
    if "Running on local URL" in line:
        ready = True
        break

if not ready:
    raise RuntimeError("App process ended before the local server came up — "
                        "check the printed output above for the real error.")

time.sleep(5)  # small buffer after the URL prints, before the server truly accepts requests

from gradio_client import Client

client = Client("http://127.0.0.1:7860")

for i, job in enumerate(jobs):
    print(f"\n=== Generating job {i+1}/{len(jobs)} ===")
    result = client.predict(
        prompt=job["prompt"],
        input_image_start=None,
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
    print(f"Job {i+1} status: {status_text}")
    # The app's own Video_Generation function already copies outputs into
    # /kaggle/working/outputs/ — nothing extra needed here for that part.

print("\nAll jobs complete. Shutting down local server and exiting.")
app_process.terminate()
try:
    app_process.wait(timeout=15)
except subprocess.TimeoutExpired:
    app_process.kill()

# Script ends here — no explicit "stop" call needed. This is the actual
# mechanism that makes Kaggle mark the kernel complete.
print("Done — this kernel run should now finish naturally.")
