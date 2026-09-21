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

class ProductionStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

class SceneStatus(Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

@dataclass
class Scene:
    scene_id: UUID
    production_id: UUID
    sequence_index: int
    generation_request: VideoGenerationRequest
    status: SceneStatus = SceneStatus.NOT_STARTED
    job_ref: Optional[str] = None
    generated_artifact: Optional[ArtifactReference] = None

    def transition_to(self, new_status: SceneStatus):
        if self.status == SceneStatus.SUCCEEDED:
            raise ValueError("Cannot transition from SUCCEEDED state.")
        if self.status == SceneStatus.FAILED:
            raise ValueError("Cannot transition from FAILED state.")
            
        if self.status == SceneStatus.NOT_STARTED and new_status not in [SceneStatus.RUNNING, SceneStatus.FAILED]:
            raise ValueError(f"Cannot transition from NOT_STARTED to {new_status}")
        if self.status == SceneStatus.RUNNING and new_status not in [SceneStatus.SUCCEEDED, SceneStatus.FAILED]:
            raise ValueError(f"Cannot transition from RUNNING to {new_status}")
            
        self.status = new_status

@dataclass
class Production:
    production_id: UUID
    title: str
    channel_id: str
    status: ProductionStatus = ProductionStatus.CREATED
    scenes: list[Scene] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.validate()

    def validate(self):
        if not self.scenes:
            return
        
        indices = [scene.sequence_index for scene in self.scenes]
        indices_sorted = sorted(indices)
        
        expected = list(range(len(self.scenes)))
        if indices_sorted != expected:
            raise ValueError(f"Invalid sequence indices: expected {expected}, got {indices_sorted}")
            
        for i, scene in enumerate(self.scenes):
            if scene.sequence_index != i:
                raise ValueError(f"Scene at index {i} has sequence_index {scene.sequence_index} instead of {i}")

    def transition_to(self, new_status: ProductionStatus):
        if self.status == ProductionStatus.SUCCEEDED:
            raise ValueError("Cannot transition from SUCCEEDED state.")
        if self.status == ProductionStatus.FAILED:
            raise ValueError("Cannot transition from FAILED state.")
        
        if self.status == ProductionStatus.CREATED and new_status not in [ProductionStatus.RUNNING, ProductionStatus.FAILED]:
            raise ValueError(f"Cannot transition from CREATED to {new_status}")
        if self.status == ProductionStatus.RUNNING and new_status not in [ProductionStatus.SUCCEEDED, ProductionStatus.FAILED]:
            raise ValueError(f"Cannot transition from RUNNING to {new_status}")
            
        self.status = new_status
        self.updated_at = datetime.utcnow()

