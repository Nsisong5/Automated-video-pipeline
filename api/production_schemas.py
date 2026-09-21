from pydantic import BaseModel
from typing import Optional

class SceneRequestSchema(BaseModel):
    prompt: str
    duration_seconds: int

class CreateProductionSchema(BaseModel):
    title: str
    channel_id: str
    scenes: list[SceneRequestSchema]

class ProductionResponseSchema(BaseModel):
    production_id: str
    status: str
