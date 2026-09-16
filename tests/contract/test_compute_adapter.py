import unittest
from application.ports import ComputeJobStatus
from infrastructure.compute.kaggle.fakes import FakeKaggleComputeAdapter

class TestComputeAdapterContract(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeKaggleComputeAdapter()

    def test_distinguish_network_error_from_failure(self):
        # This test ensures adapters must distinguish these
        job_id = self.adapter.submit({})
        
        self.adapter.simulate_failure(ComputeJobStatus.UNKNOWN_NETWORK_ERROR)
        self.assertEqual(self.adapter.get_status(job_id), ComputeJobStatus.UNKNOWN_NETWORK_ERROR)
        
        self.adapter.simulate_failure(ComputeJobStatus.FAILED)
        self.assertEqual(self.adapter.get_status(job_id), ComputeJobStatus.FAILED)

if __name__ == '__main__':
    unittest.main()
