from uuid import uuid4, UUID
from application.ports import VideoGenerationPort, ProviderCapabilities
from domain.entities import VideoGenerationRequest, GenerationResult, JobStatus
from datetime import datetime

class FakeVideoGenerationAdapter:
    def __init__(self):
        self.jobs = {}
        self.capabilities = {ProviderCapabilities.TEXT_TO_VIDEO}

    def submit(self, request: VideoGenerationRequest) -> UUID:
        job_id = uuid4()
        self.jobs[job_id] = JobStatus.QUEUED
        return job_id

    def get_status(self, job_id: UUID) -> JobStatus:
        return self.jobs.get(job_id, JobStatus.FAILED)

    def get_result(self, job_id: UUID) -> GenerationResult:
        return GenerationResult([], 0.0, "fake", datetime.utcnow())

    def get_capabilities(self) -> set[ProviderCapabilities]:
        return self.capabilities
