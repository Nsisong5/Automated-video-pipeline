import logging
from fastapi import APIRouter, Depends, HTTPException
from api.schemas import VideoGenerationRequestSchema, VideoGenerationResponseSchema
from api.dependencies import get_request_use_case, get_status_use_case, get_result_use_case
from domain.entities import VideoGenerationRequest
from uuid import UUID

logger = logging.getLogger(__name__)
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
    logger.info(f"API: request_generation received - prompt='{schema.prompt[:60]}...'")
    job_id = use_case.execute(request)
    logger.info(f"[job_id={job_id}] API: request_generation processed")
    return {"job_id": str(job_id), "status": "REQUESTED"}

@router.get("/video-generations/{job_id}")
async def get_status(job_id: UUID, use_case = Depends(get_status_use_case)):
    logger.info(f"[job_id={job_id}] API: get_status requested")
    status = use_case.execute(job_id)
    logger.info(f"[job_id={job_id}] API: get_status returning {status.value}")
    return {"job_id": str(job_id), "status": status.value}

@router.get("/video-generations/{job_id}/result")
async def get_result(job_id: UUID, use_case = Depends(get_result_use_case)):
    logger.info(f"[job_id={job_id}] API: get_result requested")
    try:
        result = use_case.execute(job_id)
        logger.info(f"[job_id={job_id}] API: get_result successful")
        return result
    except ValueError as e:
        logger.warning(f"[job_id={job_id}] API: get_result failed (409/404) - error='{e}'")
        if "not successful" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
