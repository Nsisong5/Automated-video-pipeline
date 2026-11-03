import time
import os
import sys
import json
import logging
from uuid import UUID
from domain.entities import VideoGenerationRequest, ProductionStatus
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from infrastructure.generation.ltx25.adapter import LTXVideoGenerationAdapter
from infrastructure.persistence.production_repository import JsonFileProductionRepository
from infrastructure.storage.local.adapter import LocalArtifactStorageAdapter
from infrastructure.media.ffmpeg.client import FfmpegClient
from infrastructure.media.ffmpeg.adapter import FFmpegFrameExtractionAdapter, FFmpegVideoAssemblyAdapter
from application.use_cases import CreateProduction, StartProduction, GetProductionStatus

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 1. Setup
prod_repo = JsonFileProductionRepository(db_path="productions.json")
compute_adapter = KaggleComputeAdapter()
gen_adapter = LTXVideoGenerationAdapter(compute_adapter=compute_adapter)
storage_adapter = LocalArtifactStorageAdapter(storage_dir="generated_clips")
frame_port = FFmpegFrameExtractionAdapter(FfmpegClient())
assembly_port = FFmpegVideoAssemblyAdapter(FfmpegClient())

create_uc = CreateProduction(prod_repo)
start_uc = StartProduction(prod_repo, gen_adapter)
status_uc = GetProductionStatus(prod_repo, gen_adapter, storage_adapter, frame_port, assembly_port)

# 2. Load Scenes
PROMPT_FILE = "prompt.txt"
if not os.path.exists(PROMPT_FILE):
    logger.error(f"Prompt file not found: {PROMPT_FILE}")
    sys.exit(1)

with open(PROMPT_FILE, "r") as f:
    scenes_data = json.load(f)

requests = []
for s in scenes_data:
    req = VideoGenerationRequest(
        prompt=s["prompt"], 
        duration_seconds=s["duration_seconds"],
        chain_from_previous=s.get("chain_from_previous", False),
        input_video_strength=s.get("input_video_strength")
    )
    requests.append(req)

# Create Production
prod_id = create_uc.execute("Test Production", "ch1", requests)
logger.info(f"Created production: {prod_id}")

# 3. Start
start_uc.execute(prod_id)
logger.info("Production started.")

# 4. Wait/Poll
POLL_INTERVAL = 30
logger.info(f"Starting poll every {POLL_INTERVAL}s...")

for _ in range(120): # Max poll time
    prod = status_uc.execute(prod_id)
    logger.info(f"Status: {prod.status.value}")
    
    if prod.status == ProductionStatus.SUCCEEDED:
        logger.info(f"Production succeeded!")
        if prod.final_artifact:
            logger.info(f"Final episode: {prod.final_artifact.location}")
        sys.exit(0)
    elif prod.status == ProductionStatus.FAILED:
        logger.error("Production failed.")
        sys.exit(1)
        
    time.sleep(POLL_INTERVAL)

logger.error("Timed out.")
sys.exit(1)
