import unittest
from uuid import uuid4
from infrastructure.generation.wan2gp.adapter import Wan2GPVideoGenerationAdapter
from infrastructure.compute.kaggle.fakes import FakeKaggleComputeAdapter
from domain.entities import VideoGenerationRequest

class TestWan2GPAdapter(unittest.TestCase):
    def setUp(self):
        self.fake_compute = FakeKaggleComputeAdapter()
        self.adapter = Wan2GPVideoGenerationAdapter(compute_adapter=self.fake_compute)

    def test_submit_translates_request(self):
        request = VideoGenerationRequest(prompt="test prompt", duration_seconds=5)
        job_id = self.adapter.submit(request)
        self.assertIsNotNone(job_id)
        # Verify job was submitted to compute
        self.assertIn(job_id, self.fake_compute.jobs)

if __name__ == '__main__':
    unittest.main()
