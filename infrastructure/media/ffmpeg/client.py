import subprocess
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class FfmpegClient:
    def run(self, cmd: list[str]) -> str:
        logger.info(f"FfmpegClient: Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FfmpegClient: Failed. Stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg command failed: {' '.join(cmd)}")
        return result.stdout
