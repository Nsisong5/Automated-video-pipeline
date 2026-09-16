from typing import Any
from uuid import uuid4
from application.ports import ArtifactStoragePort
from domain.entities import ArtifactReference, StorageKind

class FakeLocalArtifactStorageAdapter:
    def __init__(self):
        self.storage = {}

    def store(self, local_path: str, metadata: dict[str, Any]) -> ArtifactReference:
        ref = ArtifactReference(artifact_id=str(uuid4()), storage_kind=StorageKind.LOCAL, location=local_path)
        self.storage[ref.artifact_id] = local_path
        return ref

    def retrieve(self, ref: ArtifactReference) -> str:
        return self.storage[ref.artifact_id]

    def exists(self, ref: ArtifactReference) -> bool:
        return ref.artifact_id in self.storage
