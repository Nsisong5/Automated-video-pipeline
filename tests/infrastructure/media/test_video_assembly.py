import unittest
import os
import shutil
from unittest.mock import MagicMock
from domain.entities import ArtifactReference, StorageKind
from infrastructure.media.ffmpeg.client import FfmpegClient
from infrastructure.media.ffmpeg.adapter import FFmpegVideoAssemblyAdapter

class TestVideoAssembly(unittest.TestCase):
    def setUp(self):
        self.output_dir = "test_episodes"
        self.ffmpeg_client = MagicMock(spec=FfmpegClient)
        self.adapter = FFmpegVideoAssemblyAdapter(self.ffmpeg_client, output_dir=self.output_dir)
        
        # Create dummy clips
        self.clips = []
        for i in range(2):
            path = f"clip_{i}.mp4"
            with open(path, "w") as f: f.write("content")
            self.clips.append(ArtifactReference(f"id_{i}", StorageKind.LOCAL, path))

    def tearDown(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        for clip in self.clips:
            if os.path.exists(clip.location):
                os.remove(clip.location)

    def test_assemble_clips(self):
        def side_effect(cmd):
            # Verify concat file creation - cmd: ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, ...]
            # Index 7 is the concat file path
            concat_file = cmd[7]
            self.assertTrue(os.path.exists(concat_file))
            # Mock success
            return ""
        
        self.ffmpeg_client.run.side_effect = side_effect
        
        episode_ref = self.adapter.assemble(self.clips)
        
        self.assertTrue(episode_ref.location.startswith(self.output_dir))
        self.ffmpeg_client.run.assert_called_once()

if __name__ == '__main__':
    unittest.main()
