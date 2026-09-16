from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

class JobStatus(Enum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_RECOVERING = "UNKNOWN_RECOVERING"

class StorageKind(Enum):
    LOCAL = "LOCAL"

@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    storage_kind: StorageKind
    location: str

@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    duration_seconds: int
    request_id: UUID = field(default_factory=uuid4)
    negative_prompt: Optional[str] = None
    resolution: Optional[str] = None
    aspect_ratio: Optional[str] = None
    seed: Optional[int] = None
    start_frame: Optional[ArtifactReference] = None
    end_frame: Optional[ArtifactReference] = None
    idempotency_key: Optional[str] = None

@dataclass
class GenerationResult:
    output_artifacts: list[ArtifactReference]
    duration_seconds_actual: float
    provider_name: str
    generated_at: datetime

@dataclass
class GenerationError:
    message: str
    provider_error_code: Optional[str] = None

@dataclass
class GenerationJob:
    job_id: UUID
    request: VideoGenerationRequest
    status: JobStatus = JobStatus.REQUESTED
    external_ref: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    result: Optional[GenerationResult] = None
    error: Optional[GenerationError] = None

    def transition_to(self, new_status: JobStatus, provider_error: Optional[GenerationError] = None):
        # Enforce lifecycle rules
        if self.status == JobStatus.FAILED:
            raise ValueError("Cannot transition from FAILED state.")
        
        # Rule: Only explicit provider failure can trigger FAILED
        if new_status == JobStatus.FAILED and provider_error is None:
            raise ValueError("FAILED status requires an explicit GenerationError.")
            
        self.status = new_status
        self.updated_at = datetime.utcnow()
        if provider_error:
            self.error = provider_error
