import os
from dataclasses import dataclass

@dataclass
class Settings:
    GENERATION_PROVIDER: str = os.getenv("GENERATION_PROVIDER", "wan2gp_kaggle")
    KAGGLE_ACCOUNTS_DIR: str = os.getenv("KAGGLE_ACCOUNTS_DIR", os.path.expanduser("~/.kaggle/accounts/"))
    ARTIFACT_STORAGE_DIR: str = os.getenv("ARTIFACT_STORAGE_DIR", "generated_clips")
    JOB_DB_PATH: str = os.getenv("JOB_DB_PATH", "jobs.json")

settings = Settings()
