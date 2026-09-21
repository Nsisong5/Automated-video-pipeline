import logging
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from domain.entities import VideoGenerationRequest
from api.production_schemas import CreateProductionSchema, ProductionResponseSchema
from api.dependencies import (
    get_create_production_use_case,
    get_start_production_use_case,
    get_production_status_use_case,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/productions", response_model=ProductionResponseSchema)
async def create_production(
    schema: CreateProductionSchema,
    use_case = Depends(get_create_production_use_case)
):
    requests = [
        VideoGenerationRequest(prompt=s.prompt, duration_seconds=s.duration_seconds)
        for s in schema.scenes
    ]
    production_id = use_case.execute(schema.title, schema.channel_id, requests)
    logger.info(f"[production_id={production_id}] API: Production created")
    return {"production_id": str(production_id), "status": "CREATED"}

@router.post("/productions/{production_id}/start")
async def start_production(
    production_id: UUID,
    use_case = Depends(get_start_production_use_case)
):
    use_case.execute(production_id)
    logger.info(f"[production_id={production_id}] API: Production started")
    return {"status": "RUNNING"}

@router.get("/productions/{production_id}/status")
async def get_production_status(
    production_id: UUID,
    use_case = Depends(get_production_status_use_case)
):
    production = use_case.execute(production_id)
    logger.info(f"[production_id={production_id}] API: Returning status {production.status.value}")
    return {
        "production_id": str(production_id),
        "status": production.status.value,
        "scenes": [
            {
                "sequence_index": s.sequence_index,
                "status": s.status.value,
                "artifact": s.generated_artifact.location if s.generated_artifact else None
            } for s in production.scenes
        ]
    }
