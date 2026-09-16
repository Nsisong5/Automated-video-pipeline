"""
Full backend-driven cycle:
  1. Check if a run is already in flight (survives backend disconnects —
     restarting this script won't spin up a duplicate instance).
  2. If not: rotate to the next Kaggle account, push the job request,
     start the notebook.
  3. Poll until it completes.
  4. Download the generated clips.
  5. Delete the job-request dataset now that it's been consumed.
"""

import os
import json

from infrastructure.compute.kaggle.accounts import get_next_account
from infrastructure.compute.kaggle.notebook_control import (
    push_job_request, start_notebook, wait_for_completion, get_status,
    fetch_outputs, delete_dataset, JOB_DATASET_SLUG,
)

ACTIVE_RUN_FILE = "active_run_state.json"


def _get_resumable_username() -> str | None:
    """Returns the username of an in-flight run to resume, or None if
    there's nothing to resume (safe to start a fresh one)."""
    if not os.path.exists(ACTIVE_RUN_FILE):
        return None
    with open(ACTIVE_RUN_FILE) as f:
        state = json.load(f)
    username = state.get("username")
    if not username:
        return None
    status_text = get_status(username).lower()
    if "running" in status_text or "queued" in status_text:
        return username
    # Stale record from a run that already finished/errored — safe to clear.
    os.remove(ACTIVE_RUN_FILE)
    return None


def _save_active_run(username: str) -> None:
    with open(ACTIVE_RUN_FILE, "w") as f:
        json.dump({"username": username}, f)


def _clear_active_run() -> None:
    if os.path.exists(ACTIVE_RUN_FILE):
        os.remove(ACTIVE_RUN_FILE)


def run_cycle(jobs: list[dict]):
    resumed_username = _get_resumable_username()

    if resumed_username:
        username = resumed_username
        print(f"\n=== Resuming existing in-flight run under: {username} "
              f"(not starting a new one, not re-pushing jobs) ===")
    else:
        account = get_next_account()
        username = account["username"]
        print(f"\n=== Starting a fresh run under: {username} ===")
        push_job_request(username, jobs)
        start_notebook(username)
        _save_active_run(username)

    print("\n=== Waiting for notebook to finish ===")
    outcome = wait_for_completion(username)

    if outcome == "error":
        print("❌ Notebook run ended in error — check the notebook's logs on "
              "kaggle.com before trusting any partial output.")
        _clear_active_run()
        return None

    print("\n=== Fetching output ===")
    output_dir = fetch_outputs(username)

    print("\n=== Cleaning up job-request dataset ===")
    delete_dataset(username, JOB_DATASET_SLUG)

    _clear_active_run()
    print(f"\n✅ Cycle complete. Output in: {output_dir}")
    return output_dir


if __name__ == "__main__":
    run_cycle([
        {
            "prompt": "A futuristic robot walking down a neon street, cinematic lighting",
            "duration": "2 Seconds (49 frames - Fast)",
            "resolution": "Fast Preview (384p - ~1-2 min)",
        },
    ])
