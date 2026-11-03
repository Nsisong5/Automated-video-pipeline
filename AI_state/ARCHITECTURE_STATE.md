# ARCHITECTURE STATE

- `domain/`: Entities including `Job`, `Request`, `Artifact`, `Result`, `Error`, `ReferenceAsset`, `ReferenceCreation`, `ReferenceCreationMethod`, and production/scene validation invariants.
- `application/`: Ports (`VideoGenerationPort`, `ComputeExecutionPort`, `ProviderCapabilities.REFERENCE_ASSETS`, etc.) and use cases (`CreateProduction`, `StartProduction`, `GetProductionStatus`).
- `infrastructure/`: Adapters (Kaggle, LTX25, FFmpeg, Persistence, Storage) supporting extended job schema with reference assets and client job IDs.
- `api/`: FastAPI delivery layer supporting strict input validation (`extra='forbid'`, `jobs`/`scenes` union normalisation).
