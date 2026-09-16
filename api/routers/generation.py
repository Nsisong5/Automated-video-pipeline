from fastapi import APIRouter, Depends, HTTPException
from api.schemas import VideoGenerationRequestSchema, VideoGenerationResponseSchema
from api.dependencies import get_request_use_case, get_status_use_case, get_result_use_case
from domain.entities import VideoGenerationRequest
from uuid import UUID

router = APIRouter()

@router.post("/video-generations", response_model=VideoGenerationResponseSchema)
async def request_generation(
    schema: VideoGenerationRequestSchema,
    use_case = Depends(get_request_use_case)
):
    request = VideoGenerationRequest(
        prompt=schema.prompt,
        duration_seconds=schema.duration_seconds,
        resolution=schema.resolution,
        seed=schema.seed
    )
    job_id = use_case.execute(request)
    return {"job_id": str(job_id), "status": "REQUESTED"}

@router.get("/video-generations/{job_id}")
async def get_status(job_id: UUID, use_case = Depends(get_status_use_case)):
    status = use_case.execute(job_id)
    return {"job_id": str(job_id), "status": status.value}

@router.get("/video-generations/{job_id}/result")
async def get_result(job_id: UUID, use_case = Depends(get_result_use_case)):
    try:
        result = use_case.execute(job_id)
        return result
    except ValueError as e:
        if "not successful" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
