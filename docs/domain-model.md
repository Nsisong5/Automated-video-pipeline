# Domain Model Specification

## Core Entities & Value Objects

### Production
- `production_id`: UUID
- `title`: str
- `channel_id`: str
- `status`: ProductionStatus (`CREATED`, `RUNNING`, `ASSEMBLING`, `SUCCEEDED`, `FAILED`)
- `scenes`: list[Scene]
- `reference_assets`: tuple[ReferenceAsset, ...]
- `final_artifact`: Optional[ArtifactReference]

### Scene
- `scene_id`: UUID
- `production_id`: UUID
- `sequence_index`: int
- `generation_request`: VideoGenerationRequest
- `status`: SceneStatus (`NOT_STARTED`, `RUNNING`, `SUCCEEDED`, `FAILED`)
- `client_job_id`: Optional[str] (client's custom key, `^[A-Za-z0-9_-]{1,64}$`)

### ReferenceAsset
- `asset_id`: str (`^[A-Za-z0-9_-]{1,64}$`, unique within production)
- `creation`: ReferenceCreation
- `required`: Optional[bool]
- `name`: Optional[str]
- `category`: Optional[str]

### ReferenceCreation
- `method`: ReferenceCreationMethod (`GENERATE`, `UPLOAD`)
- `prompt`: Optional[str] (required when method = generate)
- `negative_prompt`: Optional[str]
- `aspect_ratio`: Optional[str]
- `uploaded_image_ref`: Optional[str] (required when method = upload)

### VideoGenerationRequest
- `prompt`: str
- `duration_seconds`: int
- `resolution`: Optional[str] (opaque pass-through string)
- `aspect_ratio`: Optional[str] (opaque pass-through string)
- `seed`: Optional[int]
- `reference_asset_ids`: tuple[str, ...] (each must reference an asset in `Production.reference_assets`)
