import json
from uuid import UUID, uuid4
from typing import Any
from datetime import datetime
from application.ports import VideoGenerationPort, ComputeExecutionPort, ProviderCapabilities, ComputeWorkload
from domain.entities import VideoGenerationRequest, GenerationResult, JobStatus, ArtifactReference, StorageKind

class Wan2GPVideoGenerationAdapter:
    def __init__(self, compute_adapter: ComputeExecutionPort):
        self.compute_adapter = compute_adapter
        self.capabilities = {
            ProviderCapabilities.TEXT_TO_VIDEO,
            ProviderCapabilities.SEED_CONTROL,
            ProviderCapabilities.DURATION_CONTROL,
        }

    def submit(self, request: VideoGenerationRequest) -> UUID:
        # Map integer duration_seconds to exact string choices expected by Gradio/Notebook headless runner
        duration_mapping = {
            2: "2 Seconds (49 frames - Fast)",
            3: "3 Seconds (73 frames - Standard)",
            5: "5 Seconds (121 frames - Long)",
            8: "8 Seconds (193 frames)",
            10: "10 Seconds (241 frames)"
        }
        
        # Snap to the closest supported duration
        supported_durations = sorted(duration_mapping.keys())
        target = request.duration_seconds
        # Find the key with the minimum absolute difference
        closest_duration = min(supported_durations, key=lambda x: abs(x - target))
        
        duration_str = duration_mapping[closest_duration]
        
        # Map resolution to exact string choice expected by Gradio/Notebook headless runner
        resolution_str = request.resolution or "Fast Preview (384p - ~1-2 min)"
        if "384" in resolution_str:
            resolution_str = "Fast Preview (384p - ~1-2 min)"

        # Translate domain request to notebook JSON
        job_data = {
            "prompt": request.prompt,
            "duration": duration_str,
            "resolution": resolution_str,
            "seed": request.seed or -1,
        }
        
        # Use injected compute adapter to trigger the workload
        return self.compute_adapter.submit(ComputeWorkload(jobs=[job_data]))

    def get_status(self, job_id: UUID) -> JobStatus:
        # Map compute status to domain job status
        compute_status = self.compute_adapter.get_status(job_id)
        
        mapping = {
            "RUNNING": JobStatus.RUNNING,
            "QUEUED": JobStatus.QUEUED,
            "SUCCEEDED": JobStatus.SUCCEEDED,
            "FAILED": JobStatus.FAILED,
            "UNKNOWN_NETWORK_ERROR": JobStatus.UNKNOWN_RECOVERING,
        }
        
        return mapping.get(compute_status.name, JobStatus.UNKNOWN_RECOVERING)

    def get_result(self, job_id: UUID) -> GenerationResult:
        # Get artifacts from compute, translate to GenerationResult
        artifacts = self.compute_adapter.get_result(job_id)
        
        return GenerationResult(
            output_artifacts=artifacts,
            duration_seconds_actual=0.0, # Placeholder
            provider_name="wan2gp_kaggle",
            generated_at=datetime.utcnow()
        )

    def get_capabilities(self) -> set[ProviderCapabilities]:
        return self.capabilities
