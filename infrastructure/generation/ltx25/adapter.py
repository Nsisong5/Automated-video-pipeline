import json
from uuid import UUID, uuid4
from typing import Any, Sequence
from datetime import datetime
from application.ports import VideoGenerationPort, ComputeExecutionPort, ProviderCapabilities, ComputeWorkload
from domain.entities import VideoGenerationRequest, GenerationResult, JobStatus, ArtifactReference, StorageKind, ReferenceAsset

class LTXVideoGenerationAdapter:
    def __init__(self, compute_adapter: ComputeExecutionPort):
        self.compute_adapter = compute_adapter
        self.capabilities = {
            ProviderCapabilities.TEXT_TO_VIDEO,
            ProviderCapabilities.SEED_CONTROL,
            ProviderCapabilities.DURATION_CONTROL,
            ProviderCapabilities.REFERENCE_ASSETS,
        }

    def submit(self, requests: list[VideoGenerationRequest], reference_assets: Sequence[ReferenceAsset] = ()) -> UUID:
        ref_assets_data = []
        for asset in reference_assets:
            creation_dict = {
                "method": asset.creation.method.value
            }
            if asset.creation.prompt is not None:
                creation_dict["prompt"] = asset.creation.prompt
            if asset.creation.negative_prompt is not None:
                creation_dict["negative_prompt"] = asset.creation.negative_prompt
            if asset.creation.aspect_ratio is not None:
                creation_dict["aspect_ratio"] = asset.creation.aspect_ratio
            if asset.creation.uploaded_image_ref is not None:
                creation_dict["uploaded_image_ref"] = asset.creation.uploaded_image_ref

            asset_dict = {
                "asset_id": asset.asset_id,
                "creation": creation_dict
            }
            if asset.required is not None:
                asset_dict["required"] = asset.required
            if asset.name is not None:
                asset_dict["name"] = asset.name
            if asset.category is not None:
                asset_dict["category"] = asset.category

            ref_assets_data.append(asset_dict)

        jobs_data = []
        for req in requests:
            duration_mapping = {
                2: "2 Seconds (49 frames - Fast)",
                3: "3 Seconds (73 frames - Standard)",
                5: "5 Seconds (121 frames - Long)",
                8: "8 Seconds (193 frames)",
                10: "10 Seconds (241 frames)"
            }
            supported_durations = sorted(duration_mapping.keys())
            target = req.duration_seconds
            closest_duration = min(supported_durations, key=lambda x: abs(x - target))
            
            job_data = {
                "prompt": req.prompt,
                "duration_seconds": req.duration_seconds,
                "duration": duration_mapping[closest_duration],
                "chain_from_previous": req.chain_from_previous
            }
            if req.client_job_id:
                job_data["job_id"] = req.client_job_id
            if req.resolution:
                job_data["resolution"] = req.resolution
            if req.aspect_ratio:
                job_data["aspect_ratio"] = req.aspect_ratio
            if req.seed is not None:
                job_data["seed"] = req.seed
            if req.input_video_strength is not None:
                job_data["input_video_strength"] = float(req.input_video_strength)
            if req.reference_asset_ids:
                job_data["reference_asset_ids"] = list(req.reference_asset_ids)

            jobs_data.append(job_data)

        # Submit all jobs as one workload batch
        return self.compute_adapter.submit(ComputeWorkload(jobs=jobs_data, reference_assets=ref_assets_data))

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
            provider_name="ltx25_kaggle",
            generated_at=datetime.utcnow()
        )

    def get_capabilities(self) -> set[ProviderCapabilities]:
        return self.capabilities
