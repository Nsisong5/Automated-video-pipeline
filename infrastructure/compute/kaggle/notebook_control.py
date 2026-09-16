"""
Backend-side control of the Kaggle notebook lifecycle. No hardcoded
username anywhere — the active account's username (set by kaggle_accounts.
get_next_account()) is used to build every owner/slug reference.
"""

import os
import json
import time
import subprocess

KERNEL_SLUG = "ltx-video"  # confirmed from your actual kernel-metadata.json 'id' field
JOB_DATASET_SLUG = "ltx-job-request"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.stdout.strip():
        print(result.stdout)
    if result.returncode != 0 and result.stderr.strip():
        print("stderr:", result.stderr)
    return result


def push_job_request(username: str, jobs: list[dict]) -> None:
    """jobs: list of dicts like
    {"prompt": "...", "duration": "2 Seconds (49 frames - Fast)",
     "resolution": "Fast Preview (384p - ~1-2 min)", "seed": -1}
    """
    stage = "job_request_stage"
    os.makedirs(stage, exist_ok=True)
    with open(f"{stage}/jobs.json", "w") as f:
        json.dump({"jobs": jobs}, f, indent=2)

    dataset_id = f"{username}/{JOB_DATASET_SLUG}"
    metadata_path = f"{stage}/dataset-metadata.json"

    # Does it already exist for this account? If not, create; else version.
    status = _run(["kaggle", "datasets", "status", "-d", dataset_id])
    exists = status.returncode == 0

    if not exists:
        with open(metadata_path, "w") as f:
            json.dump({
                "title": "LTX job request queue",
                "id": dataset_id,
                "licenses": [{"name": "other"}],
            }, f)
        _run(["kaggle", "datasets", "create", "-p", stage])
    else:
        if not os.path.exists(metadata_path):
            with open(metadata_path, "w") as f:
                json.dump({
                    "title": "LTX job request queue",
                    "id": dataset_id,
                    "licenses": [{"name": "other"}],
                }, f)
        _run(["kaggle", "datasets", "version", "-p", stage, "-m", "new job batch"])

    print(f"Pushed {len(jobs)} job(s) to {dataset_id}")


def delete_dataset(username: str, slug: str) -> bool:
    dataset_id = f"{username}/{slug}"
    # -d isn't accepted by this delete subcommand on the installed CLI
    # version (confirmed: "unrecognized arguments: -d") — positional matches
    # how every other kaggle command here already works.
    result = _run(["kaggle", "datasets", "delete", dataset_id, "--yes"])
    if result.returncode == 0:
        print(f"Deleted dataset: {dataset_id}")
        return True
    print(f"Could not delete {dataset_id} — check the syntax with "
          f"`kaggle datasets delete --help` if this keeps failing.")
    return False


def start_notebook(username: str) -> None:
    """Pulls the notebook's CURRENT content (whatever you've built up across
    Steps 1-4 in the Kaggle UI) and pushes it again to trigger a fresh run.
    This avoids needing to duplicate your notebook's cell content here —
    whatever's saved on Kaggle is what runs."""
    kernel_ref = f"{username}/{KERNEL_SLUG}"
    pull_dir = "notebook_pull"
    os.makedirs(pull_dir, exist_ok=True)

    pull_result = _run(["kaggle", "kernels", "pull", kernel_ref, "-p", pull_dir, "-m"])
    if pull_result.returncode != 0:
        raise RuntimeError(
            f"kernel pull failed for {kernel_ref} (see the error above — "
            f"often a wrong slug or a permissions issue). Not proceeding, "
            f"since continuing would mean pushing stale/incorrect data."
        )

    # API-triggered runs (via push) don't necessarily inherit the browser
    # session's accelerator setting — force it explicitly rather than
    # trusting whatever came down in the pulled metadata.
    metadata_path = os.path.join(pull_dir, "kernel-metadata.json")
    with open(metadata_path) as f:
        metadata = json.load(f)
    print(f"Pulled kernel-metadata.json BEFORE forcing GPU: {metadata}")

    metadata["enable_gpu"] = True
    metadata["enable_internet"] = True

    # A controlled comparison test found the one real difference between a
    # kernel that got a GPU and one that didn't: the working one had no
    # pinned docker_image at all. A frozen image pinned by digest could be
    # old enough that its PyTorch build genuinely isn't CUDA-compiled,
    # independent of whether Kaggle attaches a physical GPU. Drop the pin so
    # this uses Kaggle's current default image instead.
    if "docker_image" in metadata:
        print(f"Removing pinned docker_image: {metadata['docker_image']}")
        del metadata["docker_image"]

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"kernel-metadata.json AFTER forcing GPU + dropping image pin: {metadata}")

    # The .ipynb file carries its OWN separate embedded accelerator record
    # (metadata.kaggle.accelerator / isGpuEnabled / isInternetEnabled) —
    # this is what the browser's "Settings -> Accelerator" actually edits,
    # and it can be out of sync with kernel-metadata.json above. Patch it
    # directly rather than trusting the sidecar file alone.
    notebook_filename = metadata.get("code_file")
    if not notebook_filename:
        raise RuntimeError("kernel-metadata.json has no 'code_file' entry — can't "
                            "find the .ipynb to patch its embedded metadata.")
    notebook_path = os.path.join(pull_dir, notebook_filename)

    with open(notebook_path) as f:
        notebook = json.load(f)

    kaggle_block = notebook.get("metadata", {}).get("kaggle", {})
    print(f"Notebook's OWN embedded accelerator metadata BEFORE patch: {kaggle_block}")

    notebook.setdefault("metadata", {}).setdefault("kaggle", {})
    notebook["metadata"]["kaggle"]["accelerator"] = "gpu"
    notebook["metadata"]["kaggle"]["isGpuEnabled"] = True
    notebook["metadata"]["kaggle"]["isInternetEnabled"] = True

    with open(notebook_path, "w") as f:
        json.dump(notebook, f)

    print(f"Notebook's embedded accelerator metadata AFTER patch: "
          f"{notebook['metadata']['kaggle']}")

    _run(["kaggle", "kernels", "push", "-p", pull_dir])
    print(f"Triggered a fresh run of {kernel_ref}")


def get_status(username: str) -> str:
    kernel_ref = f"{username}/{KERNEL_SLUG}"
    result = _run(["kaggle", "kernels", "status", kernel_ref])
    return result.stdout.strip()


def wait_for_completion(username: str, timeout_seconds: int = 2400,
                         poll_interval: int = 30) -> str:
    """Polls status until it reports complete or error. Model loading alone
    has taken several minutes in your runs, plus generation time per job —
    default timeout is generous (40 min).

    Local network blips (e.g. this backend's own connection dropping) must
    NOT be treated the same as Kaggle reporting the kernel itself failed —
    an earlier version of this function did exactly that, because exception
    text like 'NameResolutionError' contains the substring 'error' and got
    caught by a naive check. That silently discarded a run that was actually
    still succeeding on Kaggle's side. Now: network-failure text is detected
    explicitly and treated as transient (keep waiting), and 'error' is only
    trusted as a genuine kernel failure when it's part of Kaggle's own
    reported status text, not a connection exception's message."""
    start = time.time()
    network_failure_markers = (
        "nameresolutionerror", "max retries exceeded", "connectionerror",
        "temporary failure in name resolution", "failed to resolve",
        "connection aborted", "remote end closed connection",
        "connection refused", "timed out",
    )
    while time.time() - start < timeout_seconds:
        status_text = get_status(username).lower()
        elapsed = time.time() - start
        print(f"  status check at {elapsed:.0f}s: {status_text}")

        if any(marker in status_text for marker in network_failure_markers):
            print("  ⚠️ That looks like a LOCAL network problem on this end, not "
                  "something Kaggle reported about the kernel itself. Treating "
                  "this as transient — not giving up on the run.")
            time.sleep(poll_interval)
            continue

        if "complete" in status_text:
            return "complete"
        if "kernelworkerstatus.error" in status_text or "kernelworkerstatus.failed" in status_text:
            return "error"

        time.sleep(poll_interval)
    raise TimeoutError(f"Notebook did not reach a final status within {timeout_seconds}s")


def fetch_outputs(username: str, dest_dir: str = "notebook_outputs") -> str:
    kernel_ref = f"{username}/{KERNEL_SLUG}"
    os.makedirs(dest_dir, exist_ok=True)
    _run(["kaggle", "kernels", "output", kernel_ref, "-p", dest_dir])
    print(f"Downloaded kernel output to {dest_dir}")
    return dest_dir
