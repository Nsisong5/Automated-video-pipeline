"""
The Kaggle run already finished successfully (851.6s, real output produced).
Skip the full cycle — just grab what's already there.
"""

from kaggle_accounts import get_next_account
from kaggle_notebook_control import fetch_outputs, get_status

account = get_next_account()
username = account["username"]

print("Current status (should show a completed/finished state now):")
print(get_status(username))

output_dir = fetch_outputs(username)
print(f"\nDownloaded to: {output_dir}")
print("Look inside for the .mp4 — per the Kaggle log it should be something like")
print("ltx25_<timestamp>_seed404229316_with_audio.mp4")
