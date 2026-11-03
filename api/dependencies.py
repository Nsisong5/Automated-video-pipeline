from api.config import settings
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from infrastructure.generation.ltx25.adapter import LTXVideoGenerationAdapter
from infrastructure.persistence.job_repository import JsonFileJobRepository
from infrastructure.persistence.production_repository import JsonFileProductionRepository
from infrastructure.storage.local.adapter import LocalArtifactStorageAdapter
from infrastructure.media.ffmpeg.adapter import FFmpegFrameExtractionAdapter, FFmpegVideoAssemblyAdapter
from infrastructure.media.ffmpeg.client import FfmpegClient
from application.use_cases import (
    RequestVideoGeneration, GetGenerationStatus, GetGenerationResult,
    CreateProduction, StartProduction, GetProductionStatus as GetProductionStatusUseCase
)

# Simple dependency injection
def get_job_repo():
    return JsonFileJobRepository(db_path=settings.JOB_DB_PATH)

def get_production_repo():
    return JsonFileProductionRepository(db_path="productions.json")

def get_compute_adapter():
    return KaggleComputeAdapter()

def get_storage_adapter():
    return LocalArtifactStorageAdapter(storage_dir=settings.ARTIFACT_STORAGE_DIR)

def get_generation_port():
    return LTXVideoGenerationAdapter(compute_adapter=get_compute_adapter())

def get_request_use_case():
    return RequestVideoGeneration(get_generation_port(), get_job_repo())

def get_status_use_case():
    return GetGenerationStatus(get_generation_port(), get_job_repo())

def get_result_use_case():
    return GetGenerationResult(get_generation_port(), get_job_repo())

def get_create_production_use_case():
    return CreateProduction(get_production_repo())

def get_start_production_use_case():
    return StartProduction(get_production_repo(), get_generation_port())

def get_production_status_use_case():
    return GetProductionStatusUseCase(
        get_production_repo(), 
        get_generation_port(), 
        get_storage_adapter(),
        FFmpegVideoAssemblyAdapter(FfmpegClient())
    )
