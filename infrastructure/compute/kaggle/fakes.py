from typing import Optional, Any
from uuid import uuid4, UUID
from application.ports import ComputeExecutionPort, ComputeJobStatus
from domain.entities import ArtifactReference

class FakeKaggleComputeAdapter:
    def __init__(self):
        self.jobs = {}
        self.forced_status = None

    def submit(self, workload: Any) -> UUID:
        job_id = uuid4()
        self.jobs[job_id] = ComputeJobStatus.QUEUED
        return job_id

    def get_status(self, job_id: UUID) -> ComputeJobStatus:
        return self.forced_status or self.jobs.get(job_id, ComputeJobStatus.FAILED)

    def get_result(self, job_id: UUID) -> list[ArtifactReference]:
        return []
        
    def simulate_failure(self, status: ComputeJobStatus):
        self.forced_status = status
