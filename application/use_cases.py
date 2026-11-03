import logging
import dataclasses
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, Sequence
from domain.entities import (
    VideoGenerationRequest, GenerationJob, JobStatus, GenerationResult, GenerationError,
    Production, Scene, ProductionStatus, SceneStatus, ArtifactReference,
    ReferenceAsset, ReferenceCreationMethod
)
from application.ports import (
    VideoGenerationPort, JobRepositoryPort, ProductionRepositoryPort, 
    ArtifactStoragePort, FrameExtractionPort, VideoAssemblyPort,
    ProviderCapabilities
)

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

class CreateProduction:
    def __init__(self, repo: ProductionRepositoryPort):
        self.repo = repo

    def execute(self, title: str, channel_id: str, requests: list[VideoGenerationRequest], reference_assets: Sequence[ReferenceAsset] = ()) -> UUID:
        for asset in reference_assets:
            if asset.creation.method == ReferenceCreationMethod.UPLOAD:
                raise ValueError("reference asset upload is not supported yet")

        production_id = uuid4()
        scenes = [
            Scene(
                scene_id=uuid4(),
                production_id=production_id,
                sequence_index=i,
                generation_request=req,
                chain_from_previous=req.chain_from_previous,
                input_video_strength=req.input_video_strength,
                client_job_id=getattr(req, 'client_job_id', None)
            ) for i, req in enumerate(requests)
        ]
        production = Production(
            production_id=production_id,
            title=title,
            channel_id=channel_id,
            scenes=scenes,
            reference_assets=tuple(reference_assets)
        )
        self.repo.save(production)
        logger.info(f"[production_id={production_id}] CreateProduction: Created production '{title}' with {len(scenes)} scenes")
        return production_id

class StartProduction:
    def __init__(self, repo: ProductionRepositoryPort, gen_port: VideoGenerationPort):
        self.repo = repo
        self.gen_port = gen_port

    def execute(self, production_id: UUID) -> None:
        production = self.repo.get(production_id)
        if not production:
            raise ValueError("Production not found")
            
        if production.status == ProductionStatus.RUNNING:
            logger.warning(f"[production_id={production_id}] StartProduction: Already running. Skipping.")
            return

        has_refs = bool(production.reference_assets) or any(bool(s.generation_request.reference_asset_ids) for s in production.scenes)
        if has_refs:
            capabilities = self.gen_port.get_capabilities()
            if ProviderCapabilities.REFERENCE_ASSETS not in capabilities:
                raise ValueError("Provider does not support reference assets")

        # Prepare batch
        requests = []
        for scene in production.scenes:
            req = dataclasses.replace(
                scene.generation_request,
                chain_from_previous=scene.chain_from_previous,
                input_video_strength=scene.input_video_strength,
                client_job_id=scene.client_job_id
            )
            requests.append(req)

        # Submit batch
        external_ref = self.gen_port.submit(requests, reference_assets=production.reference_assets)
        
        production.external_ref = str(external_ref)
        production.transition_to(ProductionStatus.RUNNING)
        for scene in production.scenes:
            scene.transition_to(SceneStatus.RUNNING)
        
        self.repo.save(production)
        logger.info(f"[production_id={production_id}] StartProduction: Started production (batch_ref={external_ref})")

class GetProductionStatus:
    def __init__(
        self, 
        repo: ProductionRepositoryPort, 
        gen_port: VideoGenerationPort, 
        storage_port: ArtifactStoragePort,
        assembly_port: VideoAssemblyPort
    ):
        self.repo = repo
        self.gen_port = gen_port
        self.storage_port = storage_port
        self.assembly_port = assembly_port

    def execute(self, production_id: UUID) -> Production:
        production = self.repo.get(production_id)
        if not production:
            raise ValueError("Production not found")
        
        if production.status in [ProductionStatus.SUCCEEDED, ProductionStatus.FAILED]:
            return production
            
        # Poll batch kernel status
        job_status = self.gen_port.get_status(UUID(production.external_ref))
        
        if job_status == JobStatus.SUCCEEDED:
            logger.info(f"[production_id={production_id}] GetProductionStatus: Batch SUCCEEDED, fetching and assembling artifacts")
            if production.status != ProductionStatus.ASSEMBLING:
                production.transition_to(ProductionStatus.ASSEMBLING)
            self.repo.save(production)
            
            # Fetch batch results
            # The adapter should return a list of ArtifactReferences, one per scene
            try:
                batch_result = self.gen_port.get_result(UUID(production.external_ref))
            except Exception as e:
                logger.warning(f"[production_id={production_id}] GetProductionStatus: Transient error fetching batch results (will retry on next poll): {e}")
                return production

            expected_scenes_count = len(production.scenes)
            available_artifacts = batch_result.output_artifacts if batch_result and batch_result.output_artifacts else []

            # Strict all-scene verification guard: ensure ALL expected scenes are present before storing or assembling
            if len(available_artifacts) < expected_scenes_count:
                logger.warning(f"[production_id={production_id}] GetProductionStatus: Downloaded artifacts count ({len(available_artifacts)}) is less than expected scenes ({expected_scenes_count}). Waiting for complete download before assembly.")
                return production

            # Process and store each scene artifact
            scene_artifacts = []
            for i, scene in enumerate(production.scenes):
                if i < len(available_artifacts):
                    raw_artifact = available_artifacts[i]
                    
                    # Store to hierarchical path
                    artifact = self.storage_port.store(
                        raw_artifact.location,
                        {"production_id": str(production.production_id), "scene_id": str(scene.scene_id)}
                    )
                    scene.generated_artifact = artifact
                    scene.transition_to(SceneStatus.SUCCEEDED)
                    scene_artifacts.append(artifact)
            
            # Pre-assembly guard clause
            if len(scene_artifacts) < expected_scenes_count:
                logger.warning(f"[production_id={production_id}] GetProductionStatus: Stored scene artifacts count ({len(scene_artifacts)}) does not match expected ({expected_scenes_count}). Retrying on next poll.")
                return production

            # Assemble episode
            final_artifact = self.assembly_port.assemble(scene_artifacts)
            production.final_artifact = final_artifact
            
            production.transition_to(ProductionStatus.SUCCEEDED)
            self.repo.save(production)
            logger.info(f"[production_id={production_id}] GetProductionStatus: Production SUCCEEDED. Episode: {final_artifact.location}")
            
        elif job_status == JobStatus.FAILED:
            production.transition_to(ProductionStatus.FAILED)
            self.repo.save(production)
            logger.error(f"[production_id={production_id}] GetProductionStatus: Batch FAILED")
                
        return production

