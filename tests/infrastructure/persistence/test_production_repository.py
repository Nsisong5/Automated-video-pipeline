import unittest
import os
from uuid import uuid4
from domain.entities import Production, Scene, ProductionStatus, VideoGenerationRequest
from infrastructure.persistence.production_repository import JsonFileProductionRepository

class TestProductionRepository(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_productions.json"
        self.repo = JsonFileProductionRepository(db_path=self.db_path)
        
        self.request = VideoGenerationRequest(prompt="test", duration_seconds=5)
        self.scenes = [
            Scene(scene_id=uuid4(), production_id=uuid4(), sequence_index=0, generation_request=self.request),
        ]
        self.production = Production(
            production_id=uuid4(), title="Test Production", channel_id="ch1", scenes=self.scenes
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_get(self):
        self.repo.save(self.production)
        retrieved = self.repo.get(self.production.production_id)
        self.assertEqual(retrieved.production_id, self.production.production_id)
        self.assertEqual(retrieved.title, self.production.title)
        self.assertEqual(len(retrieved.scenes), 1)

    def test_find_in_flight(self):
        self.production.transition_to(ProductionStatus.RUNNING)
        self.repo.save(self.production)
        
        in_flight = self.repo.find_in_flight()
        self.assertEqual(len(in_flight), 1)
        self.assertEqual(in_flight[0].production_id, self.production.production_id)

    def test_restart_simulation(self):
        # 1. Save
        self.repo.save(self.production)
        
        # 2. Fresh instance
        new_repo = JsonFileProductionRepository(db_path=self.db_path)
        
        # 3. Retrieve
        retrieved = new_repo.get(self.production.production_id)
        self.assertEqual(retrieved.production_id, self.production.production_id)
        self.assertEqual(retrieved.title, "Test Production")

if __name__ == '__main__':
    unittest.main()
