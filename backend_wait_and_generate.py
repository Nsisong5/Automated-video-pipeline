"""
Backend-side URL fetcher. Polls the small Kaggle dataset the notebook pushes
its current Gradio URL to, waits until a (new) URL appears, then hands off
to backend_ltx_client.generate_clip using that URL.

Requires KAGGLE_USERNAME / KAGGLE_KEY set in this backend's environment too
(same credentials used everywhere else in this project).
"""

import os
import time
import subprocess

RELAY_DATASET = "wilfredjasper/ltx-gradio-url-relay"
DOWNLOAD_DIR = "gradio_url_check"


def fetch_current_url() -> str | None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", RELAY_DATASET,
         "-p", DOWNLOAD_DIR, "--unzip", "--force"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("Download failed (dataset may not exist yet):")
        print(result.stderr)
        return None

    url_file = os.path.join(DOWNLOAD_DIR, "url.txt")
    if not os.path.exists(url_file):
        print("Dataset downloaded but url.txt not found inside it.")
        return None

    with open(url_file) as f:
        return f.read().strip()


def wait_for_url(previous_url: str | None = None, timeout_seconds: int = 900,
                  poll_interval: int = 15) -> str:
    """Polls until a URL appears that's different from previous_url (or any
    URL at all, if previous_url is None). Raises TimeoutError if none shows
    up in time. Model loading alone has taken several minutes in your runs,
    so the default timeout is generous."""
    print(f"Polling for {'a new' if previous_url else 'the'} Gradio URL "
          f"(checking every {poll_interval}s, up to {timeout_seconds//60} min)...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        url = fetch_current_url()
        if url and url != previous_url:
            elapsed = time.time() - start
            print(f"Found URL after {elapsed:.0f}s: {url}")
            return url
        print(f"  ...not yet ({time.time()-start:.0f}s elapsed)")
        time.sleep(poll_interval)
    raise TimeoutError(
        f"No new URL appeared within {timeout_seconds}s — check that the "
        f"Kaggle notebook is actually running and has reached the launch step."
    )


if __name__ == "__main__":
    from backend_ltx_client import generate_clip

    url = wait_for_url()
    #print("url from dataset: ",url)
    os.environ["LTX_GRADIO_URL"] = url

    generate_clip(
        prompt="A futuristic robot walking down a neon street, cinematic lighting",
        duration="2 Seconds (49 frames - Fast)",
        resolution="Fast Preview (384p - ~1-2 min)",
    )
    