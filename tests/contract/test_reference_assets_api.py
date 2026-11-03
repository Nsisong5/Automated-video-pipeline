import unittest
from fastapi.testclient import TestClient
from api.main import app

class TestReferenceAssetsApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_post_appendix_a_payload(self):
        appendix_a = {
          "reference_assets": [
            {
              "asset_id": "cyber_scout_vehicle",
              "required": True,
              "creation": {
                "method": "generate",
                "prompt": "A heavily modified futuristic hover-bike.",
                "aspect_ratio": "16:9"
              }
            }
          ],
          "jobs": [
            {
              "job_id": "test_scene_01",
              "prompt": "The hover-bike idles inches above a neon street.",
              "duration_seconds": 5,
              "chain_from_previous": False,
              "reference_asset_ids": ["cyber_scout_vehicle"],
              "aspect_ratio": "16:9 Landscape",
              "resolution": "Fast Preview (384p - ~1-2 min)",
              "seed": 42
            }
          ]
        }
        response = self.client.post("/productions", json=appendix_a)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn("production_id", data)
        self.assertEqual(data["status"], "CREATED")

    def test_legacy_payload_still_works(self):
        legacy_body = {
            "title": "Legacy Production",
            "channel_id": "default",
            "scenes": [
                {
                    "prompt": "Legacy prompt",
                    "duration_seconds": 5,
                    "chain_from_previous": False
                }
            ]
        }
        response = self.client.post("/productions", json=legacy_body)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertIn("production_id", data)

    def test_both_jobs_and_scenes_rejected(self):
        body = {
            "jobs": [{"prompt": "p", "duration_seconds": 5}],
            "scenes": [{"prompt": "p", "duration_seconds": 5}]
        }
        response = self.client.post("/productions", json=body)
        self.assertEqual(response.status_code, 422)

    def test_unknown_field_rejected(self):
        body = {
            "title": "Bad Prod",
            "channel_id": "default",
            "jobs": [{"prompt": "p", "duration_seconds": 5}],
            "unknown_field": True
        }
        response = self.client.post("/productions", json=body)
        self.assertEqual(response.status_code, 422)

    def test_upload_method_rejected(self):
        body = {
            "reference_assets": [
                {
                    "asset_id": "char_1",
                    "creation": {
                        "method": "upload",
                        "uploaded_image_ref": "img.png"
                    }
                }
            ],
            "jobs": [{"prompt": "p", "duration_seconds": 5}]
        }
        response = self.client.post("/productions", json=body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not supported yet", response.json()["detail"])

    def test_title_and_channel_id_defaults(self):
        body = {
            "jobs": [{"job_id": "job_default_test", "prompt": "default check", "duration_seconds": 5}]
        }
        response = self.client.post("/productions", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        prod_id = data["production_id"]

        start_resp = self.client.post(f"/productions/{prod_id}/start")
        self.assertEqual(start_resp.status_code, 200)

        # Check status response includes client_job_id (job_id)
        status_resp = self.client.get(f"/productions/{prod_id}/status")
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertEqual(status_data["scenes"][0]["job_id"], "job_default_test")

if __name__ == '__main__':
    unittest.main()
