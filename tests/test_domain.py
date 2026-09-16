import unittest
from uuid import uuid4
from domain.entities import GenerationJob, VideoGenerationRequest, JobStatus, GenerationError

class TestGenerationJob(unittest.TestCase):
    def setUp(self):
        self.request = VideoGenerationRequest(prompt="test", duration_seconds=5)
        self.job = GenerationJob(job_id=uuid4(), request=self.request)

    def test_transition_to_valid(self):
        self.job.transition_to(JobStatus.QUEUED)
        self.assertEqual(self.job.status, JobStatus.QUEUED)

    def test_transition_to_failed_without_error(self):
        with self.assertRaises(ValueError):
            self.job.transition_to(JobStatus.FAILED)

    def test_transition_to_failed_with_error(self):
        err = GenerationError("Failed")
        self.job.transition_to(JobStatus.FAILED, provider_error=err)
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertEqual(self.job.error, err)

    def test_cannot_transition_from_failed(self):
        err = GenerationError("Failed")
        self.job.transition_to(JobStatus.FAILED, provider_error=err)
        with self.assertRaises(ValueError):
            self.job.transition_to(JobStatus.RUNNING)

if __name__ == '__main__':
    unittest.main()
