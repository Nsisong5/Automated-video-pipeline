from pydantic import BaseModel, Field, model_validator
from typing import Optional

class ReferenceCreationSchema(BaseModel):
    method: str
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    aspect_ratio: Optional[str] = None
    uploaded_image_ref: Optional[str] = None

    model_config = {"extra": "forbid"}

class ReferenceAssetSchema(BaseModel):
    asset_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,64}$")
    creation: ReferenceCreationSchema
    required: Optional[bool] = None
    name: Optional[str] = None
    category: Optional[str] = None

    model_config = {"extra": "forbid"}

class JobRequestSchema(BaseModel):
    prompt: str
    duration_seconds: int
    chain_from_previous: bool = False
    job_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    reference_asset_ids: list[str] = Field(default_factory=list)
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    seed: Optional[int] = None
    input_video_strength: Optional[float] = None

    model_config = {"extra": "forbid"}

class SceneRequestSchema(JobRequestSchema):
    model_config = {"extra": "forbid"}

class CreateProductionSchema(BaseModel):
    title: str = "Untitled Production"
    channel_id: str = "default"
    jobs: Optional[list[JobRequestSchema]] = None
    scenes: Optional[list[JobRequestSchema]] = None
    reference_assets: list[ReferenceAssetSchema] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_jobs_or_scenes(self) -> "CreateProductionSchema":
        if self.jobs is not None and self.scenes is not None:
            raise ValueError("Cannot provide both 'jobs' and 'scenes'. Use 'jobs'.")
        if self.jobs is None and self.scenes is None:
            raise ValueError("Either 'jobs' or 'scenes' must be provided.")
        return self

class ProductionResponseSchema(BaseModel):
    production_id: str
    status: str

    model_config = {"extra": "forbid"}
