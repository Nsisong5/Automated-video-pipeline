from pydantic import BaseModel
from typing import Optional

class VideoGenerationRequestSchema(BaseModel):
    prompt: str
    duration_seconds: int
    resolution: Optional[str] = None
    seed: Optional[int] = None

class VideoGenerationResponseSchema(BaseModel):
    job_id: str
    status: str
