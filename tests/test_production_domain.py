import unittest
from uuid import uuid4
from domain.entities import (
    Production, Scene, ProductionStatus, SceneStatus, VideoGenerationRequest
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
        self.production.transition_to(ProductionStatus.SUCCEEDED)
        self.assertEqual(self.production.status, ProductionStatus.SUCCEEDED)

    def test_production_cannot_transition_from_succeeded(self):
        self.production.transition_to(ProductionStatus.RUNNING)
        self.production.transition_to(ProductionStatus.SUCCEEDED)
        with self.assertRaises(ValueError):
            self.production.transition_to(ProductionStatus.FAILED)

if __name__ == '__main__':
    unittest.main()
