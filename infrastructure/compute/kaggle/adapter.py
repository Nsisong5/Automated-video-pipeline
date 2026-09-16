import os
import json
import subprocess
from typing import Any, Optional
from uuid import UUID, uuid4
from application.ports import ComputeExecutionPort, ComputeJobStatus, ComputeWorkload
from domain.entities import ArtifactReference, StorageKind
from infrastructure.compute.kaggle.accounts import get_next_account
from infrastructure.compute.kaggle import notebook_control

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
                return {}
        return {}

    def _save_in_flight_jobs(self):
        try:
            with open(self.persistence_file, "w") as f:
                data = {str(k): v for k, v in self.in_flight_jobs.items()}
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def submit(self, workload: ComputeWorkload) -> UUID:
        account = get_next_account()
        username = account["username"]
        job_id = uuid4()
        self.in_flight_jobs[job_id] = username
        self._save_in_flight_jobs()
        
        # 1. Prepare job request dataset
        notebook_control.push_job_request(username, workload.jobs)

        # 2. Patch metadata and push kernel
        notebook_control.start_notebook(username)
        return job_id

    def get_status(self, job_id: UUID) -> ComputeJobStatus:
        username = self.in_flight_jobs.get(job_id)
        if not username:
            return ComputeJobStatus.FAILED
            
        result = self._run_cli(["kaggle", "kernels", "status", f"{username}/ltx-video"])
        status_text = result.stdout.strip().lower()
        
        # Requirement c: status classification
        network_failure_markers = (
            "nameresolutionerror", "max retries exceeded", "connectionerror",
            "temporary failure in name resolution", "failed to resolve",
            "connection aborted", "remote end closed connection",
            "connection refused", "timed out",
        )
        
        if any(marker in status_text for marker in network_failure_markers):
            return ComputeJobStatus.UNKNOWN_NETWORK_ERROR
            
        if "complete" in status_text:
            return ComputeJobStatus.SUCCEEDED
        if "kernelworkerstatus.error" in status_text or "kernelworkerstatus.failed" in status_text:
            return ComputeJobStatus.FAILED
        if "running" in status_text or "queued" in status_text:
            return ComputeJobStatus.RUNNING
            
        # If not clearly running/queued or an error, assume still processing or transient
        return ComputeJobStatus.RUNNING

    def get_result(self, job_id: UUID) -> list[ArtifactReference]:
        if job_id in self.job_results:
            return self.job_results[job_id]

        username = self.in_flight_jobs.get(job_id)
        if not username:
            return []

        # Download results
        output_dir = f"notebook_outputs/{job_id}"
        notebook_control.fetch_outputs(username, dest_dir=output_dir)
        
        # Discover artifacts recursively
        artifacts = []
        if os.path.exists(output_dir):
            for root, _, files in os.walk(output_dir):
                for filename in files:
                    if filename.endswith((".mp4", ".mov")): 
                        artifacts.append(ArtifactReference(
                            artifact_id=f"{job_id}_{filename}",
                            storage_kind=StorageKind.LOCAL,
                            location=os.path.join(root, filename)
                        ))
        
        self.job_results[job_id] = artifacts
        return artifacts
        
    def _run_cli(self, cmd: list[str]) -> subprocess.CompletedProcess:
        # Helper for all CLI calls
        return subprocess.run(cmd, capture_output=True, text=True)


