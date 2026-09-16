import json
import os
from typing import Optional
from uuid import UUID
from application.ports import JobRepositoryPort
from domain.entities import GenerationJob, VideoGenerationRequest, JobStatus

class JsonFileJobRepository:
    def __init__(self, db_path: str = "jobs.json"):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump({}, f)

    def _load_all(self) -> dict:
        with open(self.db_path, "r") as f:
            return json.load(f)

    def _save_all(self, jobs: dict):
        with open(self.db_path, "w") as f:
            json.dump(jobs, f, indent=2)

    def save(self, job: GenerationJob) -> None:
        jobs = self._load_all()
        # Simplistic serialization for now
        jobs[str(job.job_id)] = {
            "job_id": str(job.job_id),
            "status": job.status.value,
            "external_ref": job.external_ref,
            "prompt": job.request.prompt
        }
        self._save_all(jobs)

    def get(self, job_id: UUID) -> Optional[GenerationJob]:
        jobs = self._load_all()
        data = jobs.get(str(job_id))
        if not data:
            return None
        # Reconstruction logic...
        request = VideoGenerationRequest(prompt=data["prompt"], duration_seconds=5)
        return GenerationJob(
            job_id=job_id,
            request=request,
            status=JobStatus(data["status"]),
            external_ref=data["external_ref"]
        )

    def find_in_flight(self) -> list[GenerationJob]:
        # Implementation...
        return []
