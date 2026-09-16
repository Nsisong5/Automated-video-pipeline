from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from domain.entities import VideoGenerationRequest, GenerationJob, JobStatus, GenerationResult, GenerationError
from application.ports import VideoGenerationPort, JobRepositoryPort

class RequestVideoGeneration:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, request: VideoGenerationRequest) -> UUID:
        job = GenerationJob(job_id=uuid4(), request=request, status=JobStatus.REQUESTED)
        # Persist before submit to be recoverable
        self.job_repo.save(job)
        
        try:
            external_ref = self.generation_port.submit(request)
            job.external_ref = str(external_ref)
            job.transition_to(JobStatus.QUEUED)
            self.job_repo.save(job)
        except Exception as e:
            # Handle potential failure here
            raise e
        
        return job.job_id

class GetGenerationStatus:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, job_id: UUID) -> JobStatus:
        job = self.job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")
        
        # If in a terminal state, just return it
        if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
            return job.status
            
        # Poll provider for update
        if job.external_ref:
            new_status = self.generation_port.get_status(UUID(job.external_ref))
            if new_status != job.status:
                if new_status == JobStatus.FAILED:
                    job.transition_to(new_status, provider_error=GenerationError(message="Provider reported failure"))
                else:
                    job.transition_to(new_status)
                self.job_repo.save(job)
        
        return job.status

class GetGenerationResult:
    def __init__(self, generation_port: VideoGenerationPort, job_repo: JobRepositoryPort):
        self.generation_port = generation_port
        self.job_repo = job_repo

    def execute(self, job_id: UUID) -> GenerationResult:
        job = self.job_repo.get(job_id)
        if not job or job.status != JobStatus.SUCCEEDED:
            raise ValueError("Job not found or not successful")
        
        if not job.result and job.external_ref:
            result = self.generation_port.get_result(UUID(job.external_ref))
            job.result = result
            self.job_repo.save(job)
            
        return job.result
