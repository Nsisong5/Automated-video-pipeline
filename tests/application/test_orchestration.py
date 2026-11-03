import unittest
from uuid import uuid4
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus,
    VideoGenerationRequest, ArtifactReference, StorageKind, JobStatus,
    ReferenceAsset, ReferenceCreation, ReferenceCreationMethod
)
from application.ports import VideoGenerationPort, ArtifactStoragePort, ProductionRepositoryPort, ProviderCapabilities
from application.use_cases import CreateProduction, StartProduction, GetProductionStatus

class FakeProductionRepository:
    def __init__(self): self.productions = {}
    def save(self, p): self.productions[p.production_id] = p
    def get(self, pid): return self.productions.get(pid)
    def find_in_flight(self): return [p for p in self.productions.values() if p.status == ProductionStatus.RUNNING]

class FakeVideoGenerationPort:
    def __init__(self, capabilities=None): 
        self.batch_status = JobStatus.QUEUED
        self.last_reference_assets = ()
        self.capabilities = capabilities or {ProviderCapabilities.TEXT_TO_VIDEO, ProviderCapabilities.REFERENCE_ASSETS}
    def submit(self, requests, reference_assets=()): 
        self.last_reference_assets = tuple(reference_assets)
        return uuid4()
    def get_status(self, batch_id): return self.batch_status
    def get_result(self, batch_id):
        res = MagicMock()
        res.output_artifacts = [
            ArtifactReference("art1", StorageKind.LOCAL, "clip1.mp4"),
            ArtifactReference("art2", StorageKind.LOCAL, "clip2.mp4")
        ]
        return res
    def get_capabilities(self):
        return self.capabilities

class FakeArtifactStoragePort:
    def store(self, path, meta): return ArtifactReference("s", StorageKind.LOCAL, "s.mp4")

class FakeVideoAssemblyPort:
    def assemble(self, clips): return ArtifactReference("ep", StorageKind.LOCAL, "ep.mp4")

from unittest.mock import MagicMock

class TestOrchestration(unittest.TestCase):
    def setUp(self):
        self.repo = FakeProductionRepository()
        self.gen_port = FakeVideoGenerationPort()
        self.storage = FakeArtifactStoragePort()
        self.assembly = FakeVideoAssemblyPort()
        
        self.create_uc = CreateProduction(self.repo)
        self.start_uc = StartProduction(self.repo, self.gen_port)
        self.status_uc = GetProductionStatus(self.repo, self.gen_port, self.storage, self.assembly)
        
        self.requests = [VideoGenerationRequest("p0", 1), VideoGenerationRequest("p1", 1)]
        self.prod_id = self.create_uc.execute("Title", "ch1", self.requests)

    def test_batched_flow(self):
        self.start_uc.execute(self.prod_id)
        
        # Poll: Still running
        prod = self.status_uc.execute(self.prod_id)
        self.assertEqual(prod.status, ProductionStatus.RUNNING)
        
        # Tick: Batch finishes
        self.gen_port.batch_status = JobStatus.SUCCEEDED
        prod = self.status_uc.execute(self.prod_id)
        
        # Batch succeeded
        self.assertEqual(prod.status, ProductionStatus.SUCCEEDED)

    def test_submit_failure_is_restartable(self):
        # Configure submit to fail first time
        original_submit = self.gen_port.submit
        def failing_submit(reqs, reference_assets=()):
            raise RuntimeError("Submission failed")
        
        self.gen_port.submit = failing_submit
        
        with self.assertRaises(RuntimeError):
            self.start_uc.execute(self.prod_id)
        
        prod = self.repo.get(self.prod_id)
        self.assertEqual(prod.status, ProductionStatus.CREATED)
        self.assertIsNone(prod.external_ref)

        # Restore submit and retry
        self.gen_port.submit = original_submit
        self.start_uc.execute(self.prod_id)
        
        prod = self.repo.get(self.prod_id)
        self.assertEqual(prod.status, ProductionStatus.RUNNING)

    def test_production_with_reference_assets_passes_to_submit(self):
        asset = ReferenceAsset(
            asset_id="char_1",
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="hero")
        )
        req = VideoGenerationRequest(prompt="s1", duration_seconds=5, reference_asset_ids=("char_1",))
        prod_id = self.create_uc.execute("P", "ch1", [req], reference_assets=(asset,))
        self.start_uc.execute(prod_id)
        self.assertEqual(len(self.gen_port.last_reference_assets), 1)
        self.assertEqual(self.gen_port.last_reference_assets[0].asset_id, "char_1")

    def test_missing_capability_rejects_before_submit(self):
        asset = ReferenceAsset(
            asset_id="char_1",
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="hero")
        )
        req = VideoGenerationRequest(prompt="s1", duration_seconds=5, reference_asset_ids=("char_1",))
        prod_id = self.create_uc.execute("P", "ch1", [req], reference_assets=(asset,))
        
        # Remove REFERENCE_ASSETS capability from fake port
        self.gen_port.capabilities = {ProviderCapabilities.TEXT_TO_VIDEO}
        
        with self.assertRaises(ValueError):
            self.start_uc.execute(prod_id)

    def test_upload_method_rejected_at_creation(self):
        asset = ReferenceAsset(
            asset_id="char_1",
            creation=ReferenceCreation(method=ReferenceCreationMethod.UPLOAD, uploaded_image_ref="img.png")
        )
        req = VideoGenerationRequest(prompt="s1", duration_seconds=5)
        with self.assertRaises(ValueError):
            self.create_uc.execute("P", "ch1", [req], reference_assets=(asset,))

if __name__ == '__main__':
    unittest.main()
