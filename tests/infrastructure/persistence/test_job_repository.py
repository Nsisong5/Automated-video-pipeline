import unittest
import os
import json
from uuid import uuid4
from infrastructure.persistence.job_repository import JsonFileJobRepository
from domain.entities import GenerationJob, VideoGenerationRequest, JobStatus

class TestJsonFileJobRepository(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_jobs.json"
        self.repo = JsonFileJobRepository(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_get_job(self):
        job_id = uuid4()
        request = VideoGenerationRequest(prompt="test prompt", duration_seconds=5)
        job = GenerationJob(job_id=job_id, request=request, external_ref="ext123")
        
        self.repo.save(job)
        
        retrieved_job = self.repo.get(job_id)
        self.assertIsNotNone(retrieved_job)
        self.assertEqual(retrieved_job.job_id, job_id)
        self.assertEqual(retrieved_job.external_ref, "ext123")
        self.assertEqual(retrieved_job.status, JobStatus.REQUESTED)

if __name__ == '__main__':
    unittest.main()
