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
        # For now, just track the reference to the existing file
        artifact_id = str(uuid4())
        logger.info(f"LocalArtifactStorageAdapter: Storing artifact - id={artifact_id}, source={local_path}, metadata={metadata}")
        
        try:
            # Placeholder for actual storage/move logic if needed
            # For now, ensure file exists
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Source file not found: {local_path}")
            
            logger.info(f"LocalArtifactStorageAdapter: Successfully stored artifact {artifact_id}")
            return ArtifactReference(
                artifact_id=artifact_id,
                storage_kind=StorageKind.LOCAL,
                location=local_path
            )
        except Exception:
            logger.exception(f"LocalArtifactStorageAdapter: Failed to store artifact from {local_path}")
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

