# Port: ComputeExecutionPort

**Purpose**: Execute a workload somewhere, independent of what the workload does.

**Interface**:
- `submit(workload: ComputeWorkload) -> UUID`
- `get_status(job_id: UUID) -> ComputeJobStatus`
- `get_result(job_id: UUID) -> list[ArtifactReference]`

**Failure Behavior**:
- MUST distinguish `UNKNOWN_NETWORK_ERROR` from `FAILED`.
