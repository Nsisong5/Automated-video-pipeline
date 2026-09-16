"""
Backend client for the LTX-2.5 Gradio app running on Kaggle.

IMPORTANT: GRADIO_URL changes every time the Kaggle notebook restarts —
it's a fresh gradio.live link each session. Update it below (or better,
pull it from an environment variable / config file) each time you relaunch
the notebook.
"""

import os
import time
import shutil
from gradio_client import Client, handle_file

GRADIO_URL = os.environ.get("LTX_GRADIO_URL", "https://faa3bb071fef9202dd.gradio.live/")
OUTPUT_DIR = "generated_clips"
os.makedirs(OUTPUT_DIR, exist_ok=True)




def generate_clip(
    prompt: str,
    seed: int = -1,
    duration: str = "2 Seconds (49 frames - Fast)",
    resolution: str = "Fast Preview (384p - ~1-2 min)",
    aspect_ratio: str = "16:9 Landscape",
    start_image_path: str | None = None,
    end_image_path: str | None = None,
    guide_scale: float = 1.0,
    audio_cfg: float = 1.0,
    num_steps: int = 8,
    gradio_url: str | None = None,
) -> str:
    """Calls the running app's /Video_Generation endpoint and returns the
    local path of the saved output clip.

    gradio_url overrides the module-level default/env-var value — pass it
    explicitly when the URL was just fetched at runtime (e.g. from
    backend_wait_and_generate.py), since environment variables set AFTER
    this module is imported won't retroactively change GRADIO_URL below."""
    
    url = gradio_url or os.environ.get("LTX_GRADIO_URL") or GRADIO_URL
    print(f"Connecting to {url} ...")
    client = Client(url)

    start_arg = handle_file(start_image_path) if start_image_path else None
    end_arg = handle_file(end_image_path) if end_image_path else None

    print(f"Requesting: '{prompt[:60]}...' | seed={seed} | {duration} | {resolution}")
    t0 = time.time()
    result = client.predict(
        prompt=prompt,
        input_image_start=start_arg,
        input_image_end=end_arg,
        seed=seed,
        duration_dropdown=duration,
        resolution_dropdown=resolution,
        aspect_ratio_dropdown=aspect_ratio,
        guide_scale=guide_scale,
        audio_cfg=audio_cfg,
        num_steps=num_steps,
        api_name="/Video_Generation",
    )
    elapsed = time.time() - t0

    video_info, status_text = result
    print(f"Status from app: {status_text}")
    print(f"Round trip took {elapsed:.1f}s")

    # video_info is a dict like {"video": "<temp path>", "subtitles": None}
    temp_video_path = video_info["video"] if isinstance(video_info, dict) else video_info

    dest_name = f"clip_{int(time.time())}_seed{seed}.mp4"
    dest_path = os.path.join(OUTPUT_DIR, dest_name)
    shutil.copy2(temp_video_path, dest_path)
    print(f"Saved locally: {dest_path}")
    return dest_path


if __name__ == "__main__":
    generate_clip(
        prompt="A futuristic robot walking down a neon street, cinematic lighting",
        duration="2 Seconds (49 frames - Fast)",
        resolution="Fast Preview (384p - ~1-2 min)",
    )
