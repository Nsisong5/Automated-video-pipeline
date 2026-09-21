
import time
import os
import sys
import logging
from uuid import UUID
from application.use_cases import RequestVideoGeneration, GetGenerationStatus, GetGenerationResult
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from infrastructure.generation.wan2gp.adapter import Wan2GPVideoGenerationAdapter
from infrastructure.persistence.job_repository import JsonFileJobRepository
from domain.entities import VideoGenerationRequest

# Configure logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 1. Setup
job_repo = JsonFileJobRepository(db_path="jobs.json")
compute_adapter = KaggleComputeAdapter()
gen_adapter = Wan2GPVideoGenerationAdapter(compute_adapter=compute_adapter)

request_use_case = RequestVideoGeneration(gen_adapter, job_repo)
status_use_case = GetGenerationStatus(gen_adapter, job_repo)
result_use_case = GetGenerationResult(gen_adapter, job_repo)

# 2. Submit
PROMPT_FILE = "prompt.txt"
if not os.path.exists(PROMPT_FILE):
    logger.error(f"Prompt file not found: {PROMPT_FILE}")
    sys.exit(1)

with open(PROMPT_FILE, "r") as f:
    prompt_text = f.read().strip()

request = VideoGenerationRequest(prompt=prompt_text, duration_seconds=5)
job_id = request_use_case.execute(request)
logger.info(f"Submitted job: {job_id}")

# 3. Wait/Poll
POLL_INTERVAL = 10
logger.info(f"Starting poll every {POLL_INTERVAL}s...")

for _ in range(60): # Poll for up to 10 mins (60 * 10s)
    status = status_use_case.execute(job_id)
    logger.info(f"Current Job Status: {status.value}")
    
    if status.value == "SUCCEEDED":
        logger.info(f"Job {job_id} succeeded. Retrieving results...")
        try:
            result = result_use_case.execute(job_id)
            if result and result.output_artifacts:
                logger.info(f"Successfully retrieved {len(result.output_artifacts)} artifact(s).")
                for art in result.output_artifacts:
                    logger.info(f"Artifact location: {art.location}")
            else:
                logger.error(f"Job succeeded but no artifacts found for {job_id}.")
        except Exception as e:
            logger.error(f"Error during result retrieval: {e}")
        sys.exit(0)
    elif status.value == "FAILED":
        logger.error(f"Job {job_id} failed.")
        sys.exit(1)
    
    time.sleep(POLL_INTERVAL)

logger.error("Timed out waiting for job completion.")
sys.exit(1)

