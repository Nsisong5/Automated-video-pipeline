# Port Protocols

This document outlines the Port Protocols (interfaces) that infrastructure adapters must implement.

## 1. VideoGenerationPort
Purpose: Request video generation without knowing the provider.

- `submit(request: VideoGenerationRequest) -> UUID`
- `get_status(job_id: UUID) -> JobStatus`
- `get_result(job_id: UUID) -> GenerationResult`
- `get_capabilities() -> set[ProviderCapabilities]`

## 2. ComputeExecutionPort
Purpose: Execute a workload on a specific provider environment.

- `submit(workload: ComputeWorkload) -> UUID`
- `get_status(job_id: UUID) -> ComputeJobStatus`
- `get_result(job_id: UUID) -> list[ArtifactReference]`

*Note: `ComputeJobStatus` explicitly distinguishes `FAILED` (provider error) from `UNKNOWN_NETWORK_ERROR` (retryable).*

## 3. ArtifactStoragePort
Purpose: Durable storage of media artifacts.

- `store(local_path: str, metadata: dict[str, Any]) -> ArtifactReference`
- `retrieve(ref: ArtifactReference) -> str`
- `exists(ref: ArtifactReference) -> bool`

## 4. JobRepositoryPort
Purpose: Persistence for `GenerationJob` lifecycle.

- `save(job: GenerationJob) -> None`
- `get(job_id: UUID) -> Optional[GenerationJob]`
- `find_in_flight() -> list[GenerationJob]`
