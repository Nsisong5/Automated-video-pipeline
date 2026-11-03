import os
import logging
from uuid import uuid4
from application.ports import FrameExtractionPort, VideoAssemblyPort
from domain.entities import ArtifactReference, StorageKind
from infrastructure.media.ffmpeg.client import FfmpegClient

logger = logging.getLogger(__name__)

class FFmpegFrameExtractionAdapter(FrameExtractionPort):
    def __init__(self, ffmpeg_client: FfmpegClient, output_dir: str = "extracted_frames"):
        self.ffmpeg_client = ffmpeg_client
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def extract_final_frame(self, video: ArtifactReference) -> ArtifactReference:
        if not os.path.exists(video.location):
            raise FileNotFoundError(f"Video file not found: {video.location}")
            
        frame_id = f"frame_{uuid4().hex}"
        output_path = os.path.join(self.output_dir, f"{frame_id}.jpg")
        
        # FFmpeg command to extract the very last frame
        cmd = [
            "ffmpeg",
            "-sseof", "-0.1",
            "-i", video.location,
            "-update", "1",
            "-q:v", "2",
            output_path
        ]
        
        self.ffmpeg_client.run(cmd)
        
        logger.info(f"Extracted final frame to {output_path}")
        return ArtifactReference(
            artifact_id=frame_id,
            storage_kind=StorageKind.LOCAL,
            location=output_path
        )

class FFmpegVideoAssemblyAdapter(VideoAssemblyPort):
    def __init__(self, ffmpeg_client: FfmpegClient, output_dir: str = "assembled_episodes"):
        self.ffmpeg_client = ffmpeg_client
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def assemble(self, ordered_clips: list[ArtifactReference]) -> ArtifactReference:
        if not ordered_clips:
            raise ValueError("No clips provided for assembly")

        episode_id = f"episode_{uuid4().hex}"
        output_path = os.path.join(self.output_dir, f"{episode_id}.mp4")

        # 1. Create a concat file
        concat_file = os.path.abspath(os.path.join(self.output_dir, f"{episode_id}.txt"))
        with open(concat_file, "w") as f:
            for clip in ordered_clips:
                f.write(f"file '{os.path.abspath(clip.location)}'\n")

        # 2. Assemble using concat demuxer
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]

        self.ffmpeg_client.run(cmd)
        os.remove(concat_file)

        logger.info(f"Assembled episode to {output_path}")
        return ArtifactReference(
            artifact_id=episode_id,
            storage_kind=StorageKind.LOCAL,
            location=output_path
        )
