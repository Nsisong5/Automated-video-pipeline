from uuid import uuid4, UUID
from typing import Sequence, Any
from application.ports import VideoGenerationPort, ProviderCapabilities
from domain.entities import VideoGenerationRequest, GenerationResult, JobStatus, ReferenceAsset
from datetime import datetime

class FakeVideoGenerationAdapter:
    def __init__(self):
        self.jobs = {}
        self.last_reference_assets = ()
        self.capabilities = {ProviderCapabilities.TEXT_TO_VIDEO, ProviderCapabilities.REFERENCE_ASSETS}

    def submit(self, requests: Any, reference_assets: Sequence[ReferenceAsset] = ()) -> UUID:
        job_id = uuid4()
        self.jobs[job_id] = JobStatus.QUEUED
        self.last_reference_assets = tuple(reference_assets)
        return job_id

    def get_status(self, job_id: UUID) -> JobStatus:
        return self.jobs.get(job_id, JobStatus.FAILED)

    def get_result(self, job_id: UUID) -> GenerationResult:
        return GenerationResult([], 0.0, "fake", datetime.utcnow())

    def get_capabilities(self) -> set[ProviderCapabilities]:
        return self.capabilities
