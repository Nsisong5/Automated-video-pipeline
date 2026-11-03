import unittest
from uuid import uuid4
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus, VideoGenerationRequest,
    ReferenceAsset, ReferenceCreation, ReferenceCreationMethod
)

class TestProductionDomain(unittest.TestCase):
    def setUp(self):
        self.request = VideoGenerationRequest(prompt="test", duration_seconds=5)
        self.scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=self.request),
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=1, generation_request=self.request),
        ]
        self.production = Production(
            production_id=uuid4(), title="Test Production", channel_id="ch1", scenes=self.scenes
        )

    def test_production_sequence_invariant_valid(self):
        # Should not raise
        self.production.validate()

    def test_production_sequence_invariant_missing(self):
        self.production.scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=self.request),
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=2, generation_request=self.request),
        ]
        with self.assertRaises(ValueError):
            self.production.validate()

    def test_production_sequence_invariant_duplicate(self):
        self.production.scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=self.request),
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=self.request),
        ]
        with self.assertRaises(ValueError):
            self.production.validate()

    def test_scene_transition_valid(self):
        scene = self.scenes[0]
        scene.transition_to(SceneStatus.RUNNING)
        self.assertEqual(scene.status, SceneStatus.RUNNING)
        scene.transition_to(SceneStatus.SUCCEEDED)
        self.assertEqual(scene.status, SceneStatus.SUCCEEDED)

    def test_production_transition_valid(self):
        self.production.transition_to(ProductionStatus.RUNNING)
        self.assertEqual(self.production.status, ProductionStatus.RUNNING)
        self.production.transition_to(ProductionStatus.ASSEMBLING)
        self.assertEqual(self.production.status, ProductionStatus.ASSEMBLING)
        self.production.transition_to(ProductionStatus.SUCCEEDED)
        self.assertEqual(self.production.status, ProductionStatus.SUCCEEDED)

    def test_production_cannot_transition_from_succeeded(self):
        self.production.transition_to(ProductionStatus.RUNNING)
        self.production.transition_to(ProductionStatus.ASSEMBLING)
        self.production.transition_to(ProductionStatus.SUCCEEDED)
        with self.assertRaises(ValueError):
            self.production.transition_to(ProductionStatus.FAILED)

    def test_reference_assets_and_client_job_ids_valid(self):
        asset = ReferenceAsset(
            asset_id="char_1",
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="a character"),
            required=True
        )
        req = VideoGenerationRequest(prompt="scene 1", duration_seconds=5, reference_asset_ids=("char_1",))
        scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=req, client_job_id="job_1")
        ]
        prod = Production(
            production_id=uuid4(), title="Ref Prod", channel_id="ch1",
            scenes=scenes, reference_assets=(asset,)
        )
        self.assertEqual(len(prod.reference_assets), 1)
        self.assertEqual(scenes[0].client_job_id, "job_1")

    def test_invalid_asset_id_format(self):
        asset = ReferenceAsset(
            asset_id="char 1", # space invalid
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="a character")
        )
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=self.scenes, reference_assets=(asset,))

    def test_duplicate_asset_ids(self):
        asset1 = ReferenceAsset(asset_id="char_1", creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="a"))
        asset2 = ReferenceAsset(asset_id="char_1", creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="b"))
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=self.scenes, reference_assets=(asset1, asset2))

    def test_generate_missing_prompt(self):
        asset = ReferenceAsset(asset_id="char_1", creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt=""))
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=self.scenes, reference_assets=(asset,))

    def test_upload_missing_image_ref(self):
        asset = ReferenceAsset(asset_id="char_1", creation=ReferenceCreation(method=ReferenceCreationMethod.UPLOAD, uploaded_image_ref=""))
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=self.scenes, reference_assets=(asset,))

    def test_invalid_client_job_id_format(self):
        req = VideoGenerationRequest(prompt="s", duration_seconds=5)
        scenes = [Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=req, client_job_id="job space")]
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=scenes)

    def test_duplicate_client_job_ids(self):
        req = VideoGenerationRequest(prompt="s", duration_seconds=5)
        scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=req, client_job_id="job_1"),
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=1, generation_request=req, client_job_id="job_1"),
        ]
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=scenes)

    def test_unknown_reference_asset_id(self):
        req = VideoGenerationRequest(prompt="s", duration_seconds=5, reference_asset_ids=("nonexistent",))
        scenes = [Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=req)]
        with self.assertRaises(ValueError):
            Production(production_id=uuid4(), title="P", channel_id="c", scenes=scenes)

if __name__ == '__main__':
    unittest.main()

