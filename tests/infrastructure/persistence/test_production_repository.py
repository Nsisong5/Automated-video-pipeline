import unittest
import os
import json
from uuid import uuid4
from domain.entities import (
    Production, Scene, ProductionStatus, VideoGenerationRequest,
    ReferenceAsset, ReferenceCreation, ReferenceCreationMethod
)
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
        self.production.scenes[0].chain_from_previous = True
        self.repo.save(self.production)
        retrieved = self.repo.get(self.production.production_id)
        self.assertEqual(retrieved.production_id, self.production.production_id)
        self.assertEqual(retrieved.scenes[0].chain_from_previous, True)
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

    def test_reference_assets_round_trip(self):
        asset = ReferenceAsset(
            asset_id="char_1",
            required=True,
            creation=ReferenceCreation(method=ReferenceCreationMethod.GENERATE, prompt="hero character")
        )
        req = VideoGenerationRequest(prompt="scene 1", duration_seconds=5, reference_asset_ids=("char_1",))
        prod_id = uuid4()
        scene = Scene(scene_id=uuid4(), production_id=prod_id, sequence_index=0, generation_request=req, client_job_id="scene_01_id")
        prod = Production(production_id=prod_id, title="Ref Production", channel_id="ch1", scenes=[scene], reference_assets=(asset,))
        
        self.repo.save(prod)
        retrieved = self.repo.get(prod_id)
        
        self.assertEqual(len(retrieved.reference_assets), 1)
        self.assertEqual(retrieved.reference_assets[0].asset_id, "char_1")
        self.assertEqual(retrieved.scenes[0].generation_request.reference_asset_ids, ("char_1",))
        self.assertEqual(retrieved.scenes[0].client_job_id, "scene_01_id")

    def test_old_format_compatibility(self):
        prod_id = uuid4()
        scene_id = uuid4()
        old_data = {
            "production_id": str(prod_id),
            "title": "Old Production",
            "channel_id": "default",
            "status": "CREATED",
            "scenes": [
                {
                    "scene_id": str(scene_id),
                    "production_id": str(prod_id),
                    "sequence_index": 0,
                    "generation_request": {
                        "prompt": "old prompt",
                        "duration_seconds": 5,
                        "chain_from_previous": False,
                        "input_video_strength": None
                    },
                    "status": "NOT_STARTED",
                    "job_ref": None,
                    "chain_from_previous": False,
                    "input_video_strength": None,
                    "generated_artifact": None
                }
            ],
            "final_artifact": None,
            "external_ref": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00"
        }
        with open(self.db_path, "w") as f:
            json.dump({str(prod_id): old_data}, f)
            
        retrieved = self.repo.get(prod_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Old Production")
        self.assertEqual(retrieved.reference_assets, ())
        self.assertEqual(retrieved.scenes[0].generation_request.reference_asset_ids, ())
        self.assertIsNone(retrieved.scenes[0].client_job_id)
