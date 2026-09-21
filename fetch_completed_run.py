
import sys
from uuid import UUID
from application.use_cases import GetGenerationStatus, GetGenerationResult
from infrastructure.compute.kaggle.adapter import KaggleComputeAdapter
from infrastructure.generation.wan2gp.adapter import Wan2GPVideoGenerationAdapter
from infrastructure.persistence.job_repository import JsonFileJobRepository

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_completed_run.py <job_id_uuid>")
        sys.exit(1)
        
    try:
        job_id = UUID(sys.argv[1])
    except ValueError:
        print("Invalid UUID format.")
        sys.exit(1)

    job_repo = JsonFileJobRepository(db_path="jobs.json")
    compute_adapter = KaggleComputeAdapter()
    gen_adapter = Wan2GPVideoGenerationAdapter(compute_adapter=compute_adapter)
    
    status_use_case = GetGenerationStatus(gen_adapter, job_repo)
    result_use_case = GetGenerationResult(gen_adapter, job_repo)
    
    print(f"Checking status for job {job_id}...")
    status = status_use_case.execute(job_id)
    print(f"Status: {status.value}")
    
    if status.value == "SUCCEEDED":
        print("Retrieving and downloading results...")
        result = result_use_case.execute(job_id)
        print(f"Successfully downloaded {len(result.output_artifacts)} video clip(s)!")
        for art in result.output_artifacts:
            print(f"Saved locally to: {art.location}")
    else:
        print(f"Job is in state '{status.value}' and cannot be fetched yet.")

if __name__ == "__main__":
    main()
