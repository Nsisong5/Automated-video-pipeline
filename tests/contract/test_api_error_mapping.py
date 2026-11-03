import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from api.main import app
from infrastructure.compute.kaggle.notebook_control import KaggleCommandError, KaggleErrorCategory
from domain.entities import Production, Scene, VideoGenerationRequest

class TestAPIErrorMapping(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("api.dependencies.get_production_repo")
    @patch("api.dependencies.get_generation_port")
    def test_auth_error_maps_to_502(self, mock_get_gen, mock_get_repo):
        prod_id = uuid4()
        prod = Production(production_id=prod_id, title="T", channel_id="c", scenes=[Scene(uuid4(), prod_id, 0, VideoGenerationRequest("p", 1))])
        
        mock_repo = MagicMock()
        mock_repo.get.return_value = prod
        mock_get_repo.return_value = mock_repo

        mock_gen = MagicMock()
        mock_gen.submit.side_effect = KaggleCommandError(
            KaggleErrorCategory.AUTH_OR_PERMISSION,
            "401 Unauthorized secret_token_xyz",
            ["kaggle", "kernels", "push"],
            1,
            "401 Unauthorized secret_token_xyz"
        )
        mock_get_gen.return_value = mock_gen

        response = self.client.post(f"/productions/{prod_id}/start")
        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertIn("detail", data)
        self.assertNotIn("secret_token_xyz", data["detail"])

    @patch("api.dependencies.get_production_repo")
    @patch("api.dependencies.get_generation_port")
    def test_network_error_maps_to_503(self, mock_get_gen, mock_get_repo):
        prod_id = uuid4()
        prod = Production(production_id=prod_id, title="T", channel_id="c", scenes=[Scene(uuid4(), prod_id, 0, VideoGenerationRequest("p", 1))])
        
        mock_repo = MagicMock()
        mock_repo.get.return_value = prod
        mock_get_repo.return_value = mock_repo

        mock_gen = MagicMock()
        mock_gen.submit.side_effect = KaggleCommandError(
            KaggleErrorCategory.NETWORK_UNREACHABLE,
            "NameResolutionError",
            ["kaggle", "kernels", "push"],
            1,
            "NameResolutionError"
        )
        mock_get_gen.return_value = mock_gen

        response = self.client.post(f"/productions/{prod_id}/start")
        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())

    def test_value_error_not_found_maps_to_404(self):
        response = self.client.post(f"/productions/{uuid4()}/start")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

if __name__ == '__main__':
    unittest.main()
