import json
import os
from typing import Any
from uuid import UUID, uuid4
from application.ports import ArtifactStoragePort
from domain.entities import ArtifactReference, StorageKind

class LocalArtifactStorageAdapter:
    def __init__(self, storage_dir: str = "generated_clips"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def store(self, local_path: str, metadata: dict[str, Any]) -> ArtifactReference:
        # For now, just track the reference to the existing file
        artifact_id = str(uuid4())
        return ArtifactReference(
            artifact_id=artifact_id,
            storage_kind=StorageKind.LOCAL,
            location=local_path
        )

    def retrieve(self, ref: ArtifactReference) -> str:
        return ref.location

    def exists(self, ref: ArtifactReference) -> bool:
        return os.path.exists(ref.location)
