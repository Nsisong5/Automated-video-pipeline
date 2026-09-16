from typing import Optional
from uuid import UUID
from application.ports import JobRepositoryPort
from domain.entities import GenerationJob

class FakeJobRepository:
    def __init__(self):
        self.jobs = {}

    def save(self, job: GenerationJob) -> None:
        self.jobs[job.job_id] = job

    def get(self, job_id: UUID) -> Optional[GenerationJob]:
        return self.jobs.get(job_id)

    def find_in_flight(self) -> list[GenerationJob]:
        return [job for job in self.jobs.values() if job.status in ["QUEUED", "RUNNING", "UNKNOWN_RECOVERING"]]
