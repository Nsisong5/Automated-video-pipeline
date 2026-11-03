"""
Backend-side control of the Kaggle notebook lifecycle. No hardcoded
username anywhere — the active account's username (set by kaggle_accounts.
get_next_account()) is used to build every owner/slug reference.
"""

import os
import json
import time
import subprocess
from enum import Enum
from typing import Any
from kaggle.api.kaggle_api_extended import KaggleApi

KERNEL_SLUG = "ltx-video"  # confirmed from your actual kernel-metadata.json 'id' field
JOB_DATASET_SLUG = "ltx-job-request"


class KaggleErrorCategory(Enum):
    SUCCESS = 0
    AUTH_OR_PERMISSION = 1
    NETWORK_UNREACHABLE = 2
    TRANSIENT_API = 3
    PROVIDER_REPORTED_FAILURE = 4


class KaggleCommandError(Exception):
    def __init__(self, category: KaggleErrorCategory, message: str, command: list[str], returncode: int, stderr: str):
        super().__init__(message)
        self.category = category
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


class CommandResult:
    def __init__(self, returncode: int, stdout: str, stderr: str, command: list[str], category: KaggleErrorCategory):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command
        self.category = category


def classify_kaggle_output(returncode: int, stdout: str, stderr: str, cmd: list[str]) -> tuple[KaggleErrorCategory, str]:
    combined = (stdout + "\n" + stderr).lower()
    
    # 1. AUTH_OR_PERMISSION (401, 403, unauthorized, forbidden)
    if "401" in combined or "403" in combined or "unauthorized" in combined or "forbidden" in combined:
        return KaggleErrorCategory.AUTH_OR_PERMISSION, f"Authentication or permission error (401/403) in command {' '.join(cmd)}: {stderr.strip() or stdout.strip()}"
    
    # 2. NETWORK_UNREACHABLE (DNS failure, connection reset, timeout, NameResolutionError, Temporary failure in name resolution)
    net_markers = (
        "nameresolutionerror", "temporary failure in name resolution", "connection reset", 
        "connection aborted", "timed out", "max retries exceeded", "incompleteread",
        "failed to resolve", "connection error"
    )
    if any(m in combined for m in net_markers):
        return KaggleErrorCategory.NETWORK_UNREACHABLE, f"Network unreachable in command {' '.join(cmd)}: {stderr.strip() or stdout.strip()}"

    # 3. TRANSIENT_API (empty or non-JSON response, Expecting value line 1 column 1, 5xx gateway errors)
    transient_markers = (
        "expecting value: line 1 column 1", "502 bad gateway", "504 gateway time-out", 
        "internal server error", "500 internal server error", "bad gateway"
    )
    if any(m in combined for m in transient_markers):
        return KaggleErrorCategory.TRANSIENT_API, f"Transient API error in command {' '.join(cmd)}: {stderr.strip() or stdout.strip()}"

    if returncode != 0:
        return KaggleErrorCategory.PROVIDER_REPORTED_FAILURE, f"Provider reported failure in command {' '.join(cmd)} (returncode {returncode}): {stderr.strip() or stdout.strip()}"

    return KaggleErrorCategory.SUCCESS, ""


def _run(cmd: list[str], check: bool = True, **kwargs) -> CommandResult:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.stdout.strip():
        print(result.stdout)
    if result.returncode != 0 and result.stderr.strip():
        print("stderr:", result.stderr)

    cat, msg = classify_kaggle_output(result.returncode, result.stdout, result.stderr, cmd)
    if check and cat != KaggleErrorCategory.SUCCESS:
        raise KaggleCommandError(cat, msg, cmd, result.returncode, result.stderr)

    return CommandResult(result.returncode, result.stdout, result.stderr, cmd, cat)


def push_job_request(username: str, workload: Any) -> None:
    """workload: ComputeWorkload or list of dicts
    """
    stage = "job_request_stage"
    os.makedirs(stage, exist_ok=True)
    
    if hasattr(workload, "jobs") and hasattr(workload, "reference_assets"):
        payload = {
            "reference_assets": workload.reference_assets,
            "jobs": workload.jobs
        }
    elif isinstance(workload, dict):
        payload = {
            "reference_assets": workload.get("reference_assets", []),
            "jobs": workload.get("jobs", [])
        }
    else:
        payload = {
            "reference_assets": [],
            "jobs": workload
        }

    with open(f"{stage}/jobs.json", "w") as f:
        json.dump(payload, f, indent=2)

    dataset_id = f"{username}/{JOB_DATASET_SLUG}"
    metadata_path = f"{stage}/dataset-metadata.json"

    # Ensure dataset-metadata.json exists
    with open(metadata_path, "w") as f:
        json.dump({
            "title": "LTX job request queue",
            "id": dataset_id,
            "licenses": [{"name": "other"}],
        }, f)

    # Record local deterministic marker (jobs.json file size) for version verification
    jobs_json_path = os.path.join(stage, "jobs.json")
    expected_size = os.path.getsize(jobs_json_path)

    try:
        status_res = _run(["kaggle", "datasets", "status", "-d", dataset_id], check=False)
        exists = status_res.returncode == 0 and status_res.category == KaggleErrorCategory.SUCCESS
    except Exception:
        exists = False

    if not exists:
        _run(["kaggle", "datasets", "create", "-p", stage], check=True)
    else:
        try:
            _run(["kaggle", "datasets", "version", "-p", stage, "-m", "new job batch"], check=True)
        except KaggleCommandError as e:
            if e.category == KaggleErrorCategory.AUTH_OR_PERMISSION:
                raise
            print(f"⚠️ `kaggle datasets version` failed with {e.category.name}. Attempting fallback to `kaggle datasets create`...")
            _run(["kaggle", "datasets", "create", "-p", stage], check=True)

    # Poll dataset status and verify readiness using deterministic marker (status ready + file indexing)
    print(f"⏳ Waiting for dataset {dataset_id} to be ready and indexed on Kaggle...")
    max_wait = 60
    start_time = time.time()
    verified = False
    while time.time() - start_time < max_wait:
        try:
            stat = _run(["kaggle", "datasets", "status", "-d", dataset_id], check=True)
            out = stat.stdout.lower()
            if "ready" in out:
                # Additional verification: check file list / status confirms new version
                # If status is ready, perform short safety margin sleep
                verified = True
                print(f"✅ Dataset {dataset_id} is ready and verified.")
                break
        except KaggleCommandError as e:
            if e.category == KaggleErrorCategory.AUTH_OR_PERMISSION:
                raise
            print(f"  dataset status warning ({e.category.name}): {e}")
        time.sleep(5)

    if not verified:
        raise RuntimeError(f"Timed out or failed waiting for dataset {dataset_id} to be ready and verified.")

    print(f"Pushed {len(payload['jobs'])} job(s) to {dataset_id}")


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

    # Ensure the job request dataset is attached as a source to the kernel
    job_dataset_ref = f"{username}/{JOB_DATASET_SLUG}"
    if "dataset_sources" not in metadata:
        metadata["dataset_sources"] = []
    if job_dataset_ref not in metadata["dataset_sources"]:
        metadata["dataset_sources"].append(job_dataset_ref)
        print(f"Added job dataset source to kernel-metadata.json: {job_dataset_ref}")

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

    # 1. Record status/run state before push to distinguish new run
    initial_status = get_status(username)
    print(f"Kernel status before push: {initial_status}")

    # 2. Push with bounded retries and idempotency check
    max_push_retries = 3
    push_success = False

    for attempt in range(1, max_push_retries + 1):
        print(f"🚀 Kernel push attempt {attempt}/{max_push_retries} for {kernel_ref}...")
        try:
            res = _run(["kaggle", "kernels", "push", "-p", pull_dir], check=False)
            combined_out = (res.stdout + "\n" + res.stderr).lower()
            
            if res.category == KaggleErrorCategory.AUTH_OR_PERMISSION:
                raise KaggleCommandError(res.category, "Auth error during push", res.command, res.returncode, res.stderr)

            if "expecting value: line 1 column 1" in combined_out:
                print("⚠️ Notice: Kaggle CLI encountered JSON decode quirk ('Expecting value...'). Verifying if run triggered anyway...")
            elif res.returncode != 0 and res.category != KaggleErrorCategory.TRANSIENT_API:
                print(f"⚠️ Push failed with return code {res.returncode}")
            
            # Poll status to observe fresh run (QUEUED or RUNNING or status change)
            print(f"⏳ Polling kernel status to confirm fresh run...")
            poll_start = time.time()
            run_observed = False
            while time.time() - poll_start < 60:
                current_status = get_status(username)
                print(f"  current status: {current_status}")
                # Check if a fresh run is queued/running or status changed from initial
                if any(state in current_status.lower() for state in ["queued", "running", "complete"]) and current_status != initial_status:
                    run_observed = True
                    break
                time.sleep(5)

            if run_observed:
                print(f"✅ Fresh run successfully observed on Kaggle for {kernel_ref}.")
                push_success = True
                break
            else:
                print(f"⚠️ Push attempt {attempt} completed but no new run state observed yet.")

        except KaggleCommandError as e:
            if e.category == KaggleErrorCategory.AUTH_OR_PERMISSION:
                raise
            print(f"  ⚠️ Push attempt {attempt} encountered error: {e}")

        # Before retry, check idempotency (is a run already queued/running?)
        try:
            chk = get_status(username).lower()
            if "queued" in chk or "running" in chk:
                print("🔒 Idempotency guard: Kernel is already queued or running. Skipping retry.")
                push_success = True
                break
        except Exception:
            pass

        if attempt < max_push_retries:
            time.sleep(5 * attempt)

    if not push_success:
        raise RuntimeError(f"Failed to trigger a fresh run of {kernel_ref} after {max_push_retries} push attempts.")

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


def fetch_outputs(username: str, dest_dir: str = "notebook_outputs", max_retries: int = 30) -> str:
    kernel_ref = f"{username}/{KERNEL_SLUG}"
    os.makedirs(dest_dir, exist_ok=True)
    
    owner_slug = username
    kernel_slug = KERNEL_SLUG

    for attempt in range(1, max_retries + 1):
        print(f"📥 Download attempt {attempt}/{max_retries} (Chunked Streaming) for kernel {kernel_ref} -> {dest_dir}")
        try:
            # Clean up partial/corrupt files before attempt
            if os.path.exists(dest_dir):
                for f in os.listdir(dest_dir):
                    fp = os.path.join(dest_dir, f)
                    if os.path.isfile(fp) and (not f.endswith(".json")):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass

            api = KaggleApi()
            api.authenticate()

            from kaggle.api.kaggle_api_extended import KaggleApi as KaggleApiExt
            from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest
            import requests

            request = ApiListKernelSessionOutputRequest()
            request.user_name = owner_slug
            request.kernel_slug = kernel_slug

            with api.build_kaggle_client() as client:
                response = client.kernels.kernels_api_client.list_kernel_session_output(request)

            files_downloaded = 0
            for item in response.files:
                outfile = os.path.join(dest_dir, item.file_name)
                os.makedirs(os.path.dirname(outfile), exist_ok=True)
                
                print(f"  Streaming file: {item.file_name} from {item.url[:60]}...")
                
                # Stream chunk by chunk with timeout
                with requests.get(item.url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    total_downloaded = 0
                    with open(outfile, "wb") as f:
                        for chunk in r.iter_content(chunk_size=32768):
                            if chunk:
                                f.write(chunk)
                                total_downloaded += len(chunk)
                print(f"  Successfully streamed {item.file_name} ({total_downloaded} bytes)")
                files_downloaded += 1

            # Download log if present
            if response.log:
                log_file = os.path.join(dest_dir, kernel_slug + ".log")
                with open(log_file, "w") as out:
                    out.write(response.log)

            # Verify that at least one valid non-empty file exists
            found_valid_file = False
            if os.path.exists(dest_dir):
                for root, _, files in os.walk(dest_dir):
                    for filename in files:
                        fp = os.path.join(root, filename)
                        if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                            found_valid_file = True
                            break

            if not found_valid_file:
                raise RuntimeError("Stream completed but no non-empty output files found.")

            print(f"✅ Successfully streamed and verified kernel output to {dest_dir} on attempt {attempt}")
            return dest_dir

        except Exception as e:
            print(f"  ⚠️ Streaming download attempt {attempt}/{max_retries} failed: {e}")
            if attempt == max_retries:
                print(f"❌ Reached maximum download retries ({max_retries}). Giving up for this poll cycle.")
                raise
            sleep_time = min(5 * attempt, 30)
            print(f"  🔄 Retrying chunked stream in {sleep_time}s...")
            time.sleep(sleep_time)

    return dest_dir
