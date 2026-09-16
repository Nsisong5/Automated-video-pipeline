import unittest
from uuid import uuid4
from domain.entities import VideoGenerationRequest
from application.use_cases import RequestVideoGeneration
from infrastructure.generation.wan2gp.fakes import FakeVideoGenerationAdapter
from infrastructure.persistence.fakes import FakeJobRepository

class TestUseCases(unittest.TestCase):
    def setUp(self):
        self.fake_gen = FakeVideoGenerationAdapter()
        self.fake_repo = FakeJobRepository()
        self.request_use_case = RequestVideoGeneration(self.fake_gen, self.fake_repo)

    def test_request_video_generation_persists_and_submits(self):
        request = VideoGenerationRequest(prompt="test prompt", duration_seconds=5)
        job_id = self.request_use_case.execute(request)
        
        job = self.fake_repo.get(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.request.prompt, "test prompt")
        self.assertIsNotNone(job.external_ref)

if __name__ == '__main__':
    unittest.main()
