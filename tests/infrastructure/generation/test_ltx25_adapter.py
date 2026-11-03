import unittest
from uuid import uuid4
from infrastructure.generation.ltx25.adapter import LTXVideoGenerationAdapter
from infrastructure.compute.kaggle.fakes import FakeKaggleComputeAdapter
from domain.entities import VideoGenerationRequest, ReferenceAsset, ReferenceCreation, ReferenceCreationMethod

class TestLTXVideoGenerationAdapter(unittest.TestCase):
    def setUp(self):
        self.fake_compute = FakeKaggleComputeAdapter()
        self.adapter = LTXVideoGenerationAdapter(compute_adapter=self.fake_compute)

    def test_submit_translates_request(self):
        request = VideoGenerationRequest(prompt="test prompt", duration_seconds=5)
        job_id = self.adapter.submit([request])
        self.assertIsNotNone(job_id)
        self.assertIn(job_id, self.fake_compute.jobs)

    def test_submit_with_reference_assets_and_client_job_id(self):
        asset = ReferenceAsset(
            asset_id="cyber_scout_vehicle",
            required=True,
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="hover-bike", aspect_ratio="16:9")
        )
        req = VideoGenerationRequest(
            prompt="idling hover-bike",
            duration_seconds=5,
            chain_from_previous=False,
            reference_asset_ids=("cyber_scout_vehicle",),
            aspect_ratio="16:9 Landscape",
            resolution="Fast Preview (384p - ~1-2 min)",
            seed=42,
            client_job_id="test_scene_01"
        )
        
        # Intercept workload passed to fake compute adapter
        submitted_workloads = []
        original_submit = self.fake_compute.submit
        def intercept_submit(workload):
            submitted_workloads.append(workload)
            return original_submit(workload)
        self.fake_compute.submit = intercept_submit

        self.adapter.submit([req], reference_assets=(asset,))
        
        self.assertEqual(len(submitted_workloads), 1)
        workload = submitted_workloads[0]
        
        self.assertEqual(len(workload.reference_assets), 1)
        self.assertEqual(workload.reference_assets[0]["asset_id"], "cyber_scout_vehicle")
        self.assertEqual(workload.reference_assets[0]["required"], True)
        self.assertEqual(workload.reference_assets[0]["creation"]["method"], "generate")
        
        self.assertEqual(len(workload.jobs), 1)
        job = workload.jobs[0]
        self.assertEqual(job["job_id"], "test_scene_01")
        self.assertEqual(job["prompt"], "idling hover-bike")
        self.assertEqual(job["duration_seconds"], 5)
        self.assertEqual(job["seed"], 42)
        self.assertEqual(job["reference_asset_ids"], ["cyber_scout_vehicle"])

    def test_golden_appendix_a(self):
        import json
        asset = ReferenceAsset(
            asset_id="cyber_scout_vehicle",
            required=True,
            creation=ReferenceCreation(
                method=ReferenceCreationMethod.GENERATE,
                prompt="A heavily modified, matte black futuristic hover-bike with aggressively angular armor plates and glowing crimson neon repulsor engines underneath. High contrast cyberpunk aesthetic, parked on wet asphalt.",
                aspect_ratio="16:9"
            )
        )
        req = VideoGenerationRequest(
            prompt="The matte black futuristic hover-bike idles inches above a rain-slicked neon street.",
            duration_seconds=5,
            chain_from_previous=False,
            reference_asset_ids=("cyber_scout_vehicle",),
            aspect_ratio="16:9 Landscape",
            resolution="Fast Preview (384p - ~1-2 min)",
            seed=42,
            client_job_id="test_scene_01"
        )

        submitted_workloads = []
        self.fake_compute.submit = lambda w: submitted_workloads.append(w) or uuid4()

        self.adapter.submit([req], reference_assets=(asset,))

        self.assertEqual(len(submitted_workloads), 1)
        workload = submitted_workloads[0]
        payload = {
            "reference_assets": workload.reference_assets,
            "jobs": workload.jobs
        }

        with open("tests/fixtures/appendix_a_jobs_json.json") as f:
            golden = json.load(f)

        self.assertEqual(payload, golden)

if __name__ == '__main__':
    unittest.main()
