import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
import json
import os
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from application.ports import ComputeJobStatus

class TestKaggleComputeAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = KaggleComputeAdapter()

    @patch("infrastructure.compute.kaggle.adapter.KaggleComputeAdapter._run_cli")
    def test_get_status_classification(self, mock_run):
        job_id = uuid4()
        self.adapter.in_flight_jobs[job_id] = "user1"
        
        # Test SUCCESS
        mock_run.return_value = MagicMock(stdout="complete", returncode=0)
        self.assertEqual(self.adapter.get_status(job_id), ComputeJobStatus.SUCCEEDED)
        
        # Test NETWORK FAILURE
        mock_run.return_value = MagicMock(stdout="temporary failure in name resolution", returncode=0)
        self.assertEqual(self.adapter.get_status(job_id), ComputeJobStatus.UNKNOWN_NETWORK_ERROR)
        
        # Test KERNEL ERROR
        mock_run.return_value = MagicMock(stdout="KernelWorkerStatus.ERROR", returncode=0)
        self.assertEqual(self.adapter.get_status(job_id), ComputeJobStatus.FAILED)


if __name__ == '__main__':
    unittest.main()
