import logging
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from domain.entities import VideoGenerationRequest, GenerationJob, JobStatus, GenerationResult, GenerationError
from application.ports import VideoGenerationPort, JobRepositoryPort

logger = logging.getLogger(__name__)

class RequestVideoGeneration:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, request: VideoGenerationRequest) -> UUID:
        job = GenerationJob(job_id=uuid4(), request=request, status=JobStatus.REQUESTED)
        logger.info(f"[job_id={job.job_id}] RequestVideoGeneration: Submitting request - prompt='{request.prompt[:60]}...'")
        self.job_repo.save(job)
        
        try:
            external_ref = self.generation_port.submit(request)
            logger.info(f"[job_id={job.job_id}] RequestVideoGeneration: VideoGenerationPort.submit() returned external_ref={external_ref}")
            job.external_ref = str(external_ref)
            job.transition_to(JobStatus.QUEUED)
            self.job_repo.save(job)
            logger.info(f"[job_id={job.job_id}] RequestVideoGeneration: Status transitioned to QUEUED")
        except Exception as e:
            logger.exception(f"[job_id={job.job_id}] RequestVideoGeneration: Failed to submit job")
            raise e
        
        return job.job_id

class GetGenerationStatus:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, job_id: UUID) -> JobStatus:
        job = self.job_repo.get(job_id)
        if not job:
            logger.error(f"[job_id={job_id}] GetGenerationStatus: Job not found")
            raise ValueError("Job not found")
        
        if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
            logger.info(f"[job_id={job_id}] GetGenerationStatus: Terminal status reached: {job.status.value}")
            return job.status
            
        if job.external_ref:
            logger.info(f"[job_id={job_id}] GetGenerationStatus: Polling provider (external_ref={job.external_ref}) - current_status={job.status.value}")
            new_status = self.generation_port.get_status(UUID(job.external_ref))
            if new_status != job.status:
                logger.info(f"[job_id={job_id}] GetGenerationStatus: Status transitioned: from={job.status.value}, to={new_status.value}")
                if new_status == JobStatus.FAILED:
                    job.transition_to(new_status, provider_error=GenerationError(message="Provider reported failure"))
                else:
                    job.transition_to(new_status)
                self.job_repo.save(job)
                
                if new_status == JobStatus.SUCCEEDED:
                    logger.info(f"[job_id={job_id}] GetGenerationStatus: Job SUCCEEDED, auto-fetching results")
                    try:
                        result = self.generation_port.get_result(UUID(job.external_ref))
                        job.result = result
                        self.job_repo.save(job)
                        logger.info(f"[job_id={job_id}] GetGenerationStatus: Auto-fetch successful")
                    except Exception as e:
                        logger.exception(f"[job_id={job_id}] GetGenerationStatus: Failed to auto-fetch result")
            else:
                logger.info(f"[job_id={job_id}] GetGenerationStatus: Polling tick - status remains {job.status.value}")
        else:
            logger.warning(f"[job_id={job_id}] GetGenerationStatus: No external_ref found for in-progress job")
        
        return job.status

class GetGenerationResult:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, job_id: UUID) -> GenerationResult:
        logger.info(f"[job_id={job_id}] GetGenerationResult: Result retrieval requested")
        job = self.job_repo.get(job_id)
        if not job or job.status != JobStatus.SUCCEEDED:
            logger.error(f"[job_id={job_id}] GetGenerationResult: Job not found or not in SUCCEEDED state (current={job.status if job else 'None'})")
            raise ValueError("Job not found or not successful")
        
        if not job.result and job.external_ref:
            logger.info(f"[job_id={job_id}] GetGenerationResult: Result missing in repo, fetching from provider (external_ref={job.external_ref})")
            try:
                result = self.generation_port.get_result(UUID(job.external_ref))
                job.result = result
                self.job_repo.save(job)
                logger.info(f"[job_id={job_id}] GetGenerationResult: Fetch successful")
            except Exception as e:
                logger.exception(f"[job_id={job_id}] GetGenerationResult: Failed to fetch result")
                raise e
        elif job.result:
            logger.info(f"[job_id={job_id}] GetGenerationResult: Returning result from repository")
            
        return job.result

