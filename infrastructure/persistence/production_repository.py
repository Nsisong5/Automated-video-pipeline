import json
import os
from typing import Optional, Any
from uuid import UUID
from application.ports import ProductionRepositoryPort
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus,
    VideoGenerationRequest, ArtifactReference, StorageKind
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
            "scenes": [
                {
                    "scene_id": str(scene.scene_id),
                    "production_id": str(scene.production_id),
                    "sequence_index": scene.sequence_index,
                    "generation_request": {
                        "prompt": scene.generation_request.prompt,
                        "duration_seconds": scene.generation_request.duration_seconds
                    },
                    "status": scene.status.value,
                    "job_ref": scene.job_ref,
                    "generated_artifact": {
                        "artifact_id": scene.generated_artifact.artifact_id,
                        "storage_kind": scene.generated_artifact.storage_kind.value,
                        "location": scene.generated_artifact.location
                    } if scene.generated_artifact else None
                } for scene in production.scenes
            ],
            "created_at": str(production.created_at),
            "updated_at": str(production.updated_at),
        }

    def _from_dict(self, data: dict) -> Production:
        scenes = [
            Scene(
                scene_id=UUID(s["scene_id"]),
                production_id=UUID(s["production_id"]),
                sequence_index=s["sequence_index"],
                generation_request=VideoGenerationRequest(
                    prompt=s["generation_request"]["prompt"],
                    duration_seconds=s["generation_request"]["duration_seconds"]
                ),
                status=SceneStatus(s["status"]),
                job_ref=s["job_ref"],
                generated_artifact=ArtifactReference(
                    artifact_id=s["generated_artifact"]["artifact_id"],
                    storage_kind=StorageKind(s["generated_artifact"]["storage_kind"]),
                    location=s["generated_artifact"]["location"]
                ) if s["generated_artifact"] else None
            ) for s in data["scenes"]
        ]
        return Production(
            production_id=UUID(data["production_id"]),
            title=data["title"],
            channel_id=data["channel_id"],
            status=ProductionStatus(data["status"]),
            scenes=scenes
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
            if data["status"] == ProductionStatus.RUNNING.value
        ]
