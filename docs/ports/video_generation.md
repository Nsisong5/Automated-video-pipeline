# Port: VideoGenerationPort

**Purpose**: Request generation of a video clip without knowing which model or provider fulfills it.

**Responsibilities**:
- Accept a `VideoGenerationRequest` DTO.
- Submit to compute provider.
- Monitor status and retrieve results.

**Interface**:
- `submit(request: VideoGenerationRequest) -> UUID`
- `get_status(job_id: UUID) -> JobStatus`
- `get_result(job_id: UUID) -> GenerationResult`
- `get_capabilities() -> set[ProviderCapabilities]`

**Failure Behavior**:
- Must distinguish between provider errors and network interruptions.
