import logging
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from domain.entities import (
    VideoGenerationRequest, ReferenceAsset, ReferenceCreation, ReferenceCreationMethod,
    ProductionStatus
)
from api.production_schemas import CreateProductionSchema, ProductionResponseSchema
from api.dependencies import (
    get_create_production_use_case,
    get_start_production_use_case,
    get_production_status_use_case,
    get_production_repo,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/productions", response_model=ProductionResponseSchema)
async def create_production(
    schema: CreateProductionSchema,
    use_case = Depends(get_create_production_use_case)
):
    job_list = schema.jobs if schema.jobs is not None else schema.scenes
    if job_list is None:
        raise HTTPException(status_code=422, detail="Either jobs or scenes must be provided")

    requests = [
        VideoGenerationRequest(
            prompt=j.prompt,
            duration_seconds=j.duration_seconds,
            chain_from_previous=j.chain_from_previous,
            input_video_strength=j.input_video_strength,
            reference_asset_ids=tuple(j.reference_asset_ids),
            aspect_ratio=j.aspect_ratio,
            resolution=j.resolution,
            seed=j.seed,
            client_job_id=j.job_id
        )
        for j in job_list
    ]

    reference_assets = [
        ReferenceAsset(
            asset_id=ra.asset_id,
            required=ra.required,
            name=ra.name,
            category=ra.category,
            creation=ReferenceCreation(
                method=ReferenceCreationMethod(ra.creation.method),
                prompt=ra.creation.prompt,
                negative_prompt=ra.creation.negative_prompt,
                aspect_ratio=ra.creation.aspect_ratio,
                uploaded_image_ref=ra.creation.uploaded_image_ref
            )
        )
        for ra in schema.reference_assets
    ]

    production_id = use_case.execute(
        title=schema.title,
        channel_id=schema.channel_id,
        requests=requests,
        reference_assets=reference_assets
    )
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
                "job_id": s.client_job_id,
                "artifact": s.generated_artifact.location if s.generated_artifact else None
            } for s in production.scenes
        ]
    }

@router.get("/productions/{production_id}/artifact")
async def get_production_artifact(
    production_id: UUID,
    use_case = Depends(get_production_status_use_case)
):
    production = use_case.execute(production_id)
    if production.status == ProductionStatus.SUCCEEDED:
        if not production.final_artifact:
            raise HTTPException(status_code=404, detail="Final artifact not found despite SUCCEEDED status")
        return production.final_artifact
    
    # Otherwise return scenes available so far
    return [
        {
            "sequence_index": s.sequence_index,
            "artifact": s.generated_artifact
        } for s in production.scenes if s.generated_artifact
    ]

@router.get("/productions")
async def list_productions(repo = Depends(get_production_repo)):
    productions = repo._load_all()
    return list(productions.values())
