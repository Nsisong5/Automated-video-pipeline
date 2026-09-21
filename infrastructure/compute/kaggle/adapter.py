import os
import json
import subprocess
import logging
from typing import Any, Optional
from uuid import UUID, uuid4
from application.ports import ComputeExecutionPort, ComputeJobStatus, ComputeWorkload
from domain.entities import ArtifactReference, StorageKind
from infrastructure.compute.kaggle.accounts import get_next_account
from infrastructure.compute.kaggle import notebook_control

logger = logging.getLogger(__name__)

class KaggleComputeAdapter:
    def __init__(self, notebook_dir: str = "infrastructure/compute/kaggle/notebook_source"):
        self.notebook_dir = notebook_dir
        self.persistence_file = "in_flight_jobs.json"
        self.in_flight_jobs = self._load_in_flight_jobs()
        self.job_results = {}  # Stores job_id -> list[ArtifactReference]

    def _load_in_flight_jobs(self) -> dict[UUID, str]:
        if os.path.exists(self.persistence_file):
            try:
                with open(self.persistence_file, "r") as f:
                    data = json.load(f)
                    return {UUID(k): v for k, v in data.items()}
            except Exception:
                logger.exception("Failed to load in-flight jobs")
                return {}
        return {}

    def _save_in_flight_jobs(self):
        try:
            with open(self.persistence_file, "w") as f:
                data = {str(k): v for k, v in self.in_flight_jobs.items()}
                json.dump(data, f, indent=2)
        except Exception:
            logger.exception("Failed to save in-flight jobs")

    def submit(self, workload: ComputeWorkload) -> UUID:
        account = get_next_account()
        username = account["username"]
        job_id = uuid4()
        kernel_ref = f"{username}/ltx-video"
        self.in_flight_jobs[job_id] = username
        self._save_in_flight_jobs()
        logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Submitting to Kaggle - account={username}, kernel_ref={kernel_ref}")

        try:
            notebook_control.push_job_request(username, workload.jobs)
            notebook_control.start_notebook(username)
            logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Submission successful")
        except Exception:
            logger.exception(f"[job_id={job_id}] KaggleComputeAdapter: Failed to submit to Kaggle")
            raise

        return job_id

    def get_status(self, job_id: UUID) -> ComputeJobStatus:
        username = self.in_flight_jobs.get(job_id)
        if not username:
            logger.warning(f"[job_id={job_id}] KaggleComputeAdapter: Status check failed - unknown user/job_id")
            return ComputeJobStatus.FAILED

        result = self._run_cli(["kaggle", "kernels", "status", f"{username}/ltx-video"])
        status_text = result.stdout.strip()
        lower_status_text = status_text.lower()

        # Requirement c: status classification
        network_failure_markers = (
            "nameresolutionerror", "max retries exceeded", "connectionerror",
            "temporary failure in name resolution", "failed to resolve",
            "connection aborted", "remote end closed connection",
            "connection refused", "timed out",
        )

        classified_status = ComputeJobStatus.RUNNING # Default to running if ambiguous

        if any(marker in lower_status_text for marker in network_failure_markers):
            classified_status = ComputeJobStatus.UNKNOWN_NETWORK_ERROR
        elif "complete" in lower_status_text:
            classified_status = ComputeJobStatus.SUCCEEDED
        elif "kernelworkerstatus.error" in lower_status_text or "kernelworkerstatus.failed" in lower_status_text:
            classified_status = ComputeJobStatus.FAILED
        elif "running" in lower_status_text or "queued" in lower_status_text:
            classified_status = ComputeJobStatus.RUNNING

        logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Status poll - raw=\"{status_text}\", classified={classified_status.name}")
        return classified_status

    def get_result(self, job_id: UUID, debug: bool = False) -> list[ArtifactReference]:
        if job_id in self.job_results:
            logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Returning cached results")
            return self.job_results[job_id]

        username = self.in_flight_jobs.get(job_id)
        if not username:
            logger.warning(f"[job_id={job_id}] KaggleComputeAdapter: Result fetch failed - unknown user/job_id")
            return []

        # Download results
        output_dir = f"notebook_outputs/{job_id}"
        logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Fetching outputs to {output_dir}")

        # Ensure we don't have a stale directory from a failed previous attempt
        if os.path.exists(output_dir):
            import shutil
            shutil.rmtree(output_dir)

        try:
            notebook_control.fetch_outputs(username, dest_dir=output_dir)
        except Exception:
            logger.exception(f"[job_id={job_id}] KaggleComputeAdapter: Failed to fetch outputs from Kaggle")
            raise

        # Discover all artifacts recursively, ignoring empty files
        raw_artifacts = []
        if os.path.exists(output_dir):
            for root, _, files in os.walk(output_dir):
                for filename in files:
                    if filename.endswith((".mp4", ".mov")): 
                        file_path = os.path.join(root, filename)
                        # Verify it is not an empty file
                        if os.path.getsize(file_path) > 0:
                            raw_artifacts.append(ArtifactReference(
                                artifact_id=f"{job_id}_{filename}",
                                storage_kind=StorageKind.LOCAL,
                                location=file_path
                            ))
                        else:
                            logger.warning(f"[job_id={job_id}] KaggleComputeAdapter: Found empty artifact file, ignoring: {file_path}")
        
        found_paths = [a.location for a in raw_artifacts]
        logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Discovery found {len(raw_artifacts)} artifacts: {found_paths}")

        if debug:
            self.job_results[job_id] = raw_artifacts
            return raw_artifacts

        # Defensive filtering for canonical artifact
        audio_artifacts = [a for a in raw_artifacts if "_with_audio.mp4" in a.location]
        plain_artifacts = [a for a in raw_artifacts if a.location.endswith(".mp4") and "_with_audio.mp4" not in a.location]

        canonical = []
        if audio_artifacts:
            # Canonical: Audio-muxed
            canonical = audio_artifacts
            logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Canonical artifact(s) identified (audio-muxed): {[a.location for a in canonical]}")
        elif plain_artifacts:
            # Fallback: Plain video
            logger.warning(f"[job_id={job_id}] KaggleComputeAdapter: Audio fallback - No audio-muxed artifact found. Using plain video(s): {[a.location for a in plain_artifacts]}")
            canonical = plain_artifacts
        else:
            logger.error(f"[job_id={job_id}] KaggleComputeAdapter: No valid artifacts found in {output_dir}")

        self.job_results[job_id] = canonical

        # CLEANUP: Delete job-request dataset now that outputs are fetched
        try:
            notebook_control.delete_dataset(username, notebook_control.JOB_DATASET_SLUG)
            logger.info(f"[job_id={job_id}] KaggleComputeAdapter: Dataset deleted for user={username}")
        except Exception:
            logger.exception(f"[job_id={job_id}] KaggleComputeAdapter: Failed to delete dataset for user={username}")

        return canonical

    def _run_cli(self, cmd: list[str]) -> subprocess.CompletedProcess:
        # Helper for all CLI calls
        return subprocess.run(cmd, capture_output=True, text=True)



