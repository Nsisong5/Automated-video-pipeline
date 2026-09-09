"""
Multi-account Kaggle credential rotation.

Setup: put each account's credentials in its own file under
~/.kaggle/accounts/, e.g.:

    ~/.kaggle/accounts/account1.json
    ~/.kaggle/accounts/account2.json

Each file is the same format Kaggle's own download gives you:
    {"username": "...", "key": "..."}

Nothing in this file (or anywhere downstream) hardcodes a username — it's
always read from whichever account file rotation currently selects.
"""

import os
import json
from pathlib import Path

ACCOUNTS_DIR = Path.home() / ".kaggle" / "accounts"
ROTATION_STATE_FILE = ACCOUNTS_DIR / ".rotation_state.json"


def list_accounts() -> list[Path]:
    if not ACCOUNTS_DIR.exists():
        raise FileNotFoundError(
            f"{ACCOUNTS_DIR} doesn't exist — create it and put your "
            f"per-account kaggle.json-style files inside."
        )
    files = sorted(p for p in ACCOUNTS_DIR.glob("*.json") if p.name != ".rotation_state.json")
    if not files:
        raise FileNotFoundError(f"No account files found in {ACCOUNTS_DIR}")
    return files


def _load_rotation_index() -> int:
    if ROTATION_STATE_FILE.exists():
        try:
            return json.loads(ROTATION_STATE_FILE.read_text()).get("last_index", -1)
        except (json.JSONDecodeError, OSError):
            return -1
    return -1


def _save_rotation_index(index: int) -> None:
    ROTATION_STATE_FILE.write_text(json.dumps({"last_index": index}))


def get_next_account() -> dict:
    """Round-robins to the next account file, sets KAGGLE_USERNAME/KAGGLE_KEY
    in the current process's environment (subprocess calls inherit this
    automatically), and returns {"username": ..., "key": ..., "file": ...}."""
    accounts = list_accounts()
    last_index = _load_rotation_index()
    next_index = (last_index + 1) % len(accounts)
    account_file = accounts[next_index]

    creds = json.loads(account_file.read_text())
    username = creds["username"]
    key = creds["key"]

    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key
    _save_rotation_index(next_index)

    print(f"Active Kaggle account: {username} (from {account_file.name}, "
          f"{next_index + 1}/{len(accounts)} in rotation)")
    return {"username": username, "key": key, "file": str(account_file)}


if __name__ == "__main__":
    account = get_next_account()
    print(account)
    