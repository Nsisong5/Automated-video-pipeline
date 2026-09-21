import unittest
import os
import shutil
from uuid import uuid4
from infrastructure.storage.local.adapter import LocalArtifactStorageAdapter

class TestLocalStorageAdapterHierarchy(unittest.TestCase):
    def setUp(self):
        self.storage_dir = "test_storage"
        self.adapter = LocalArtifactStorageAdapter(storage_dir=self.storage_dir)
        
        # Create dummy file
        self.source_file = "dummy.mp4"
        with open(self.source_file, "w") as f:
            f.write("content")

    def tearDown(self):
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)
        if os.path.exists(self.source_file):
            os.remove(self.source_file)

    def test_store_hierarchical_path(self):
        prod_id = str(uuid4())
        scene_id = str(uuid4())
        metadata = {"production_id": prod_id, "scene_id": scene_id}
        
        artifact = self.adapter.store(self.source_file, metadata)
        
        expected_path = os.path.join(self.storage_dir, "productions", prod_id, "scenes", scene_id, "video.mp4")
        self.assertEqual(artifact.location, expected_path)
        self.assertTrue(os.path.exists(expected_path))

if __name__ == '__main__':
    unittest.main()
