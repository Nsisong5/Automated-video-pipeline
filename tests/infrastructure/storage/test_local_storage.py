import unittest
from unittest.mock import patch, MagicMock
from infrastructure.storage.local.adapter import LocalArtifactStorageAdapter

class TestLocalStorageAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = LocalArtifactStorageAdapter(storage_dir="test_clips")

    @patch("infrastructure.storage.local.adapter.logger")
    @patch("infrastructure.storage.local.adapter.os.path.exists")
    def test_store_logs_exception_on_failure(self, mock_exists, mock_logger):
        mock_exists.return_value = False # Force FileNotFoundError
        
        with self.assertRaises(FileNotFoundError):
            self.adapter.store("nonexistent.mp4", {})
            
        # Verify exception was logged via logger.exception
        self.assertTrue(any("Failed to store artifact" in call.args[0] for call in mock_logger.exception.call_args_list))

if __name__ == '__main__':
    unittest.main()
