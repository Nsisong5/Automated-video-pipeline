from api.config import settings
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from infrastructure.generation.wan2gp.adapter import Wan2GPVideoGenerationAdapter
from infrastructure.persistence.job_repository import JsonFileJobRepository
from application.use_cases import RequestVideoGeneration, GetGenerationStatus, GetGenerationResult

# Simple dependency injection
def get_job_repo():
    return JsonFileJobRepository(db_path=settings.JOB_DB_PATH)

def get_compute_adapter():
    return KaggleComputeAdapter()

def get_generation_port():
    return Wan2GPVideoGenerationAdapter(compute_adapter=get_compute_adapter())

def get_request_use_case():
    return RequestVideoGeneration(get_generation_port(), get_job_repo())

def get_status_use_case():
    return GetGenerationStatus(get_generation_port(), get_job_repo())

def get_result_use_case():
    return GetGenerationResult(get_generation_port(), get_job_repo())
