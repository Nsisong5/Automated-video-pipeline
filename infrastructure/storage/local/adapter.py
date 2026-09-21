import json
import os
import logging
from typing import Any
from uuid import UUID, uuid4
from application.ports import ArtifactStoragePort
from domain.entities import ArtifactReference, StorageKind

logger = logging.getLogger(__name__)

class LocalArtifactStorageAdapter:
    def __init__(self, storage_dir: str = "generated_clips"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info(f"Initialized LocalArtifactStorageAdapter in {self.storage_dir}")

    def store(self, local_path: str, metadata: dict[str, Any]) -> ArtifactReference:
        # Module 6: Support hierarchical scene storage
        production_id = metadata.get("production_id")
        scene_id = metadata.get("scene_id")
        
        if production_id and scene_id:
            target_dir = os.path.join(self.storage_dir, "productions", production_id, "scenes", scene_id)
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, "video.mp4")
            
            import shutil
            shutil.copy2(local_path, target_path)
            actual_path = target_path
            logger.info(f"LocalArtifactStorageAdapter: Stored scene artifact to {actual_path}")
        else:
            actual_path = local_path
            logger.info(f"LocalArtifactStorageAdapter: Storing artifact at original location {actual_path}")

        artifact_id = str(uuid4())
        
        try:
            # For now, ensure file exists
            if not os.path.exists(actual_path):
                raise FileNotFoundError(f"Source/Target file not found: {actual_path}")
            
            return ArtifactReference(
                artifact_id=artifact_id,
                storage_kind=StorageKind.LOCAL,
                location=actual_path
            )
        except Exception:
            logger.exception(f"LocalArtifactStorageAdapter: Failed to store artifact from {actual_path}")
            raise

    def retrieve(self, ref: ArtifactReference) -> str:
        logger.info(f"LocalArtifactStorageAdapter: Retrieving artifact - id={ref.artifact_id}, location={ref.location}")
        if not os.path.exists(ref.location):
            logger.error(f"LocalArtifactStorageAdapter: Artifact file missing at {ref.location}")
        return ref.location

    def exists(self, ref: ArtifactReference) -> bool:
        exists = os.path.exists(ref.location)
        logger.info(f"LocalArtifactStorageAdapter: Checking existence - id={ref.artifact_id}, location={ref.location}, exists={exists}")
        return exists

