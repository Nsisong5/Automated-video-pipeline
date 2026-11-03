import json
import os
from typing import Optional, Any
from uuid import UUID
from application.ports import ProductionRepositoryPort
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus,
    VideoGenerationRequest, ArtifactReference, StorageKind,
    ReferenceAsset, ReferenceCreation, ReferenceCreationMethod
)

class JsonFileProductionRepository:
    def __init__(self, db_path: str = "productions.json"):
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump({}, f)

    def _load_all(self) -> dict:
        with open(self.db_path, "r") as f:
            return json.load(f)

    def _save_all(self, productions: dict):
        with open(self.db_path, "w") as f:
            json.dump(productions, f, indent=2)

    def _to_dict(self, production: Production) -> dict:
        return {
            "production_id": str(production.production_id),
            "title": production.title,
            "channel_id": production.channel_id,
            "status": production.status.value,
            "reference_assets": [
                {
                    "asset_id": asset.asset_id,
                    "required": asset.required,
                    "name": asset.name,
                    "category": asset.category,
                    "creation": {
                        "method": asset.creation.method.value,
                        "prompt": asset.creation.prompt,
                        "negative_prompt": asset.creation.negative_prompt,
                        "aspect_ratio": asset.creation.aspect_ratio,
                        "uploaded_image_ref": asset.creation.uploaded_image_ref
                    }
                } for asset in production.reference_assets
            ],
            "scenes": [
                {
                    "scene_id": str(scene.scene_id),
                    "production_id": str(scene.production_id),
                    "sequence_index": scene.sequence_index,
                    "generation_request": {
                        "prompt": scene.generation_request.prompt,
                        "duration_seconds": scene.generation_request.duration_seconds,
                        "chain_from_previous": scene.generation_request.chain_from_previous,
                        "input_video_strength": scene.generation_request.input_video_strength,
                        "reference_asset_ids": list(scene.generation_request.reference_asset_ids)
                    },
                    "status": scene.status.value,
                    "job_ref": scene.job_ref,
                    "chain_from_previous": scene.chain_from_previous,
                    "input_video_strength": scene.input_video_strength,
                    "client_job_id": scene.client_job_id,
                    "generated_artifact": {
                        "artifact_id": scene.generated_artifact.artifact_id,
                        "storage_kind": scene.generated_artifact.storage_kind.value,
                        "location": scene.generated_artifact.location
                    } if scene.generated_artifact else None
                } for scene in production.scenes
            ],
            "final_artifact": {
                "artifact_id": production.final_artifact.artifact_id,
                "storage_kind": production.final_artifact.storage_kind.value,
                "location": production.final_artifact.location
            } if production.final_artifact else None,
            "external_ref": production.external_ref,
            "created_at": str(production.created_at),
            "updated_at": str(production.updated_at),
        }

    def _from_dict(self, data: dict) -> Production:
        reference_assets = tuple(
            ReferenceAsset(
                asset_id=ra["asset_id"],
                required=ra.get("required"),
                name=ra.get("name"),
                category=ra.get("category"),
                creation=ReferenceCreation(
                    method=ReferenceCreationMethod(ra["creation"]["method"]),
                    prompt=ra["creation"].get("prompt"),
                    negative_prompt=ra["creation"].get("negative_prompt"),
                    aspect_ratio=ra["creation"].get("aspect_ratio"),
                    uploaded_image_ref=ra["creation"].get("uploaded_image_ref")
                )
            ) for ra in data.get("reference_assets", [])
        )
        scenes = [
            Scene(
                scene_id=UUID(s["scene_id"]),
                production_id=UUID(s["production_id"]),
                sequence_index=s["sequence_index"],
                generation_request=VideoGenerationRequest(
                    prompt=s["generation_request"]["prompt"],
                    duration_seconds=int(s["generation_request"]["duration_seconds"]),
                    chain_from_previous=bool(s.get("chain_from_previous", s["generation_request"].get("chain_from_previous", False))),
                    input_video_strength=float(s["generation_request"]["input_video_strength"]) if s["generation_request"].get("input_video_strength") is not None else None,
                    reference_asset_ids=tuple(s["generation_request"].get("reference_asset_ids", []))
                ),
                status=SceneStatus(s["status"]),
                job_ref=s["job_ref"],
                chain_from_previous=bool(s.get("chain_from_previous", False)),
                input_video_strength=float(s["input_video_strength"]) if s.get("input_video_strength") is not None else None,
                client_job_id=s.get("client_job_id"),
                generated_artifact=ArtifactReference(
                    artifact_id=s["generated_artifact"]["artifact_id"],
                    storage_kind=StorageKind(s["generated_artifact"]["storage_kind"]),
                    location=s["generated_artifact"]["location"]
                ) if s["generated_artifact"] else None
            ) for s in data["scenes"]
        ]
        final_artifact = None
        if data.get("final_artifact"):
            final_artifact = ArtifactReference(
                artifact_id=data["final_artifact"]["artifact_id"],
                storage_kind=StorageKind(data["final_artifact"]["storage_kind"]),
                location=data["final_artifact"]["location"]
            )
            
        return Production(
            production_id=UUID(data["production_id"]),
            title=data["title"],
            channel_id=data["channel_id"],
            status=ProductionStatus(data["status"]),
            scenes=scenes,
            reference_assets=reference_assets,
            final_artifact=final_artifact,
            external_ref=data.get("external_ref")
        )

    def save(self, production: Production) -> None:
        productions = self._load_all()
        productions[str(production.production_id)] = self._to_dict(production)
        self._save_all(productions)

    def get(self, production_id: UUID) -> Optional[Production]:
        productions = self._load_all()
        data = productions.get(str(production_id))
        if not data:
            return None
        return self._from_dict(data)

    def find_in_flight(self) -> list[Production]:
        productions = self._load_all()
        return [
            self._from_dict(data) 
            for data in productions.values() 
            if data["status"] in [ProductionStatus.RUNNING.value, ProductionStatus.ASSEMBLING.value]
        ]
