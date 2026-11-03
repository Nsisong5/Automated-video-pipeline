import unittest
import os
import shutil
from unittest.mock import MagicMock
from domain.entities import ArtifactReference, StorageKind
from infrastructure.media.ffmpeg.client import FfmpegClient
from infrastructure.media.ffmpeg.adapter import FFmpegFrameExtractionAdapter

class TestFrameExtraction(unittest.TestCase):
    def setUp(self):
        self.output_dir = "test_frames"
        self.ffmpeg_client = MagicMock(spec=FfmpegClient)
        self.adapter = FFmpegFrameExtractionAdapter(self.ffmpeg_client, output_dir=self.output_dir)
        
        # Create a dummy video file for path existence check
        self.dummy_video = "dummy.mp4"
        with open(self.dummy_video, "w") as f: f.write("content")

    def tearDown(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        if os.path.exists(self.dummy_video):
            os.remove(self.dummy_video)

    def test_extract_final_frame(self):
        video_ref = ArtifactReference("job_id_1", StorageKind.LOCAL, self.dummy_video)
        
        # Mock FFmpeg call to just touch the output file instead of running actual ffmpeg
        def side_effect(cmd):
            # cmd is [ffmpeg, -sseof, -1, -i, ..., output_path]
            output_path = cmd[-1]
            with open(output_path, "w") as f: f.write("fake frame")
            return ""
        
        self.ffmpeg_client.run.side_effect = side_effect
        
        frame_ref = self.adapter.extract_final_frame(video_ref)
        
        self.assertTrue(os.path.exists(frame_ref.location))
        self.assertTrue(frame_ref.location.startswith(self.output_dir))
        self.ffmpeg_client.run.assert_called_once()

if __name__ == '__main__':
    unittest.main()
