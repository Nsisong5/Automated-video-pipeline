from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
import re

class JobStatus(Enum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_RECOVERING = "UNKNOWN_RECOVERING"

class StorageKind(Enum):
    LOCAL = "LOCAL"

class ReferenceCreationMethod(Enum):
    GENERATE = "generate"
    UPLOAD = "upload"

@dataclass(frozen=True)
class ReferenceCreation:
    method: ReferenceCreationMethod
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    aspect_ratio: Optional[str] = None
    uploaded_image_ref: Optional[str] = None

@dataclass(frozen=True)
class ReferenceAsset:
    asset_id: str
    creation: ReferenceCreation
    required: Optional[bool] = None
    name: Optional[str] = None
    category: Optional[str] = None

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
    chain_from_previous: bool = False
    input_video_strength: Optional[float] = None
    reference_asset_ids: tuple[str, ...] = field(default_factory=tuple)
    client_job_id: Optional[str] = None

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
    ASSEMBLING = "ASSEMBLING"
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
    chain_from_previous: bool = False
    input_video_strength: Optional[float] = None
    client_job_id: Optional[str] = None

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
    reference_assets: tuple[ReferenceAsset, ...] = field(default_factory=tuple)
    final_artifact: Optional[ArtifactReference] = None
    external_ref: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.validate()

    def validate(self):
        asset_ids = set()
        for asset in self.reference_assets:
            if not isinstance(asset.asset_id, str) or not re.match(r"^[A-Za-z0-9_-]{1,64}$", asset.asset_id):
                raise ValueError(f"Invalid asset_id format: {asset.asset_id}")
            if asset.asset_id in asset_ids:
                raise ValueError(f"Duplicate reference asset id: {asset.asset_id}")
            asset_ids.add(asset.asset_id)

            if asset.creation.method == ReferenceCreationMethod.GENERATE:
                if not asset.creation.prompt or not asset.creation.prompt.strip():
                    raise ValueError(f"Generation reference asset {asset.asset_id} requires a non-empty prompt.")
            elif asset.creation.method == ReferenceCreationMethod.UPLOAD:
                if not asset.creation.uploaded_image_ref or not asset.creation.uploaded_image_ref.strip():
                    raise ValueError(f"Upload reference asset {asset.asset_id} requires uploaded_image_ref.")

        client_job_ids = set()
        for scene in self.scenes:
            if scene.client_job_id is not None:
                if not isinstance(scene.client_job_id, str) or not re.match(r"^[A-Za-z0-9_-]{1,64}$", scene.client_job_id):
                    raise ValueError(f"Invalid client_job_id format: {scene.client_job_id}")
                if scene.client_job_id in client_job_ids:
                    raise ValueError(f"Duplicate client_job_id: {scene.client_job_id}")
                client_job_ids.add(scene.client_job_id)

            for ref_id in scene.generation_request.reference_asset_ids:
                if ref_id not in asset_ids:
                    raise ValueError(f"Scene references unknown reference_asset_id: {ref_id}")

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
        if self.status == ProductionStatus.RUNNING and new_status not in [ProductionStatus.ASSEMBLING, ProductionStatus.FAILED]:
            raise ValueError(f"Cannot transition from RUNNING to {new_status}")
        if self.status == ProductionStatus.ASSEMBLING and new_status not in [ProductionStatus.SUCCEEDED, ProductionStatus.FAILED]:
            raise ValueError(f"Cannot transition from ASSEMBLING to {new_status}")
            
        self.status = new_status
        self.updated_at = datetime.utcnow()

