from typing import Protocol, runtime_checkable, Any, Optional
from dataclasses import dataclass
from uuid import UUID
from enum import Enum
from domain.entities import (
    VideoGenerationRequest,
    GenerationResult,
    ArtifactReference,
    JobStatus,
    GenerationJob,
)

# --- DTOs / Placeholders for Port signatures ---

class ComputeJobStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_NETWORK_ERROR = "UNKNOWN_NETWORK_ERROR"

class ProviderCapabilities(Enum):
    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    SEED_CONTROL = "SEED_CONTROL"
    DURATION_CONTROL = "DURATION_CONTROL"

@dataclass(frozen=True)
class ComputeWorkload:
    jobs: list[dict[str, Any]]


# --- Port Definitions ---

@runtime_checkable
class VideoGenerationPort(Protocol):
    def submit(self, request: VideoGenerationRequest) -> UUID: ...
    def get_status(self, job_id: UUID) -> JobStatus: ...
    def get_result(self, job_id: UUID) -> GenerationResult: ...
    def get_capabilities(self) -> set[ProviderCapabilities]: ...

@runtime_checkable
class ComputeExecutionPort(Protocol):
    def submit(self, workload: ComputeWorkload) -> UUID: ...
    def get_status(self, job_id: UUID) -> ComputeJobStatus: ...
    def get_result(self, job_id: UUID) -> list[ArtifactReference]: ...

@runtime_checkable
class ArtifactStoragePort(Protocol):
    def store(self, local_path: str, metadata: dict[str, Any]) -> ArtifactReference: ...
    def retrieve(self, ref: ArtifactReference) -> str: ...
    def exists(self, ref: ArtifactReference) -> bool: ...

@runtime_checkable
class JobRepositoryPort(Protocol):
    def save(self, job: GenerationJob) -> None: ...
    def get(self, job_id: UUID) -> Optional[GenerationJob]: ...
    def find_in_flight(self) -> list[GenerationJob]: ...
