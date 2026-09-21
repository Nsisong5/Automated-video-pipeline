import unittest
from uuid import uuid4, UUID
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus,
    VideoGenerationRequest, ArtifactReference, StorageKind, JobStatus
)
from application.ports import VideoGenerationPort, ArtifactStoragePort, ProductionRepositoryPort
from application.use_cases import CreateProduction, StartProduction, GetProductionStatus

class FakeProductionRepository:
    def __init__(self):
        self.productions = {}
    def save(self, production: Production):
        self.productions[production.production_id] = production
    def get(self, production_id: UUID):
        return self.productions.get(production_id)
    def find_in_flight(self):
        return [p for p in self.productions.values() if p.status == ProductionStatus.RUNNING]

class FakeVideoGenerationPort:
    def __init__(self):
        self.jobs = {}
    def submit(self, request):
        job_id = uuid4()
        self.jobs[job_id] = JobStatus.RUNNING
        return job_id
    def get_status(self, job_id):
        return self.jobs.get(job_id)
    def get_result(self, job_id):
        return MagicMock(output_artifacts=[ArtifactReference("art", StorageKind.LOCAL, "path/to/video.mp4")])
    def get_capabilities(self): return set()

class FakeArtifactStoragePort:
    def store(self, local_path, metadata):
        return ArtifactReference("stored_art", StorageKind.LOCAL, "stored/path/video.mp4")
    def retrieve(self, ref): return ref.location
    def exists(self, ref): return True

from unittest.mock import MagicMock

class TestOrchestration(unittest.TestCase):
    def setUp(self):
        self.repo = FakeProductionRepository()
        self.gen_port = FakeVideoGenerationPort()
        self.storage = FakeArtifactStoragePort()
        self.create_uc = CreateProduction(self.repo)
        self.start_uc = StartProduction(self.repo, self.gen_port)
        self.status_uc = GetProductionStatus(self.repo, self.gen_port, self.storage)
        
        self.requests = [VideoGenerationRequest("p1", 1), VideoGenerationRequest("p2", 1)]
        self.prod_id = self.create_uc.execute("Title", "ch1", self.requests)

    def test_lazy_tick_flow(self):
        self.start_uc.execute(self.prod_id)
        
        # Poll 1: Still running
        prod = self.status_uc.execute(self.prod_id)
        self.assertEqual(prod.scenes[0].status, SceneStatus.RUNNING)
        
        # Tick: Complete scene 0
        self.gen_port.jobs[UUID(prod.scenes[0].job_ref)] = JobStatus.SUCCEEDED
        prod = self.status_uc.execute(self.prod_id)
        
        # Should have started scene 1
        self.assertEqual(prod.scenes[0].status, SceneStatus.SUCCEEDED)
        self.assertEqual(prod.scenes[1].status, SceneStatus.RUNNING)
        self.assertIsNotNone(prod.scenes[0].generated_artifact)

if __name__ == '__main__':
    unittest.main()
