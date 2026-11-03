# Application Boundary, FastAPI, and Provider-Neutral Generation Infrastructure

Prepared by: Claude (Technical Specification Engineer)
For: Gemini CLI (Implementation)
From: Chief Engineer's module specification
Human Project Owner: Wilfred Jasper

This is the one Markdown handoff document required by the Chief Engineer's
specification. It contains architecture, ports/adapters, dependency rules,
chunked Gemini instructions, testing plan, manual verification, and the
docs-driven memory system that lets any future session (Gemini, a new Chief
Engineer, or me) resume work without re-reading this whole conversation.

**Two requirements apply to every single chunk below, not just one section,
and Gemini must not treat either as optional:**
1. **Network-interruption resilience.** Every chunk that touches a network
   call must distinguish "the remote system told us it failed" from "we
   couldn't reach it" — these are different facts. This is not a hypothetical
   concern: the real spike hit this exact bug (a local DNS failure was
   misread as "the kernel failed," discarding a run that had actually
   succeeded) and it must never be reintroduced.
2. **Docs-driven AI state.** After every chunk, the files under `AI_state/`
   (Section 17) must be updated in the same chunk, not as a follow-up. A
   fresh Gemini session must be able to read `AI_state/SESSION_HANDOFF.md`
   alone and know what to do next without this document being re-explained.

---

## 1. Executive architectural interpretation

The project is becoming a provider-neutral, multi-channel automated video
platform. Today it does one thing for real: generate a video clip via a
Kaggle notebook running Wan2GP with a DeepBeepMeep INT8-quantized LTX-2.5
model. This module's job is not to build new generation capability — it's to
put a proper application boundary (FastAPI → Application → Ports → Adapters)
around that *already-working* capability, so that:
- The application core never knows "Kaggle" or "Wan2GP" exist.
- A second provider (Veo, a hosted API, another compute environment) can be
  added later by writing a new adapter, not by touching the application core.
- Nothing about the currently-working generation path breaks in the process.

## 2. Existing-code assessment

**There is no formal repository yet.** Everything validated so far exists as:
1. A Kaggle notebook (`wilfredjasper/ltx-video`), with cells, in this order:
   Step 1 (clone Wan2GP + T4 patches) → a linking cell (symlinks a private
   Kaggle Dataset's model files into Wan2GP's expected paths) → Step 2
   (verify weights present) → Step 3 (writes the Gradio app to
   `run_aiquest_ltx25.py`) → Step 3.5 (hotfix patches) → a cell that derives
   `run_aiquest_ltx25_headless.py` from Step 3's output → a headless "Step 4"
   that reads a job-request Kaggle Dataset, generates via a local
   (non-public) Gradio call, copies output to a clean folder, deletes the
   large working directory, and exits (this natural exit is how Kaggle marks
   the run complete — there is no reliable API-based "stop a session" call).
2. Standalone Python scripts on the Human Project Owner's backend (not a
   package): account rotation, notebook control (push job / start / poll /
   fetch / cleanup), and a top-level orchestrator.
3. A separate, **incompatible** older pattern (persistent Gradio server with
   a public `gradio.live` URL relayed through a different dataset, called
   manually) — kept only for interactive testing, must never be mixed with
   the automated one-shot flow. Gemini must not resurrect this pattern
   inside the new architecture.

**Hard-won, validated facts that must be preserved exactly, not
rediscovered:**
- A Kaggle notebook carries **two independent accelerator settings**: the
  `kernel-metadata.json` sidecar (`enable_gpu`) and a separate block embedded
  *inside* the `.ipynb` file itself (`metadata.kaggle.accelerator`,
  `isGpuEnabled`, `isInternetEnabled`). Both must be patched before every
  triggered run; patching only one silently fails.
- A **pinned `docker_image` digest** in `kernel-metadata.json` can produce a
  container whose PyTorch build is not CUDA-compiled at all, independent of
  whether a physical GPU is attached — confirmed by a controlled A/B test.
  Do not pin a docker image unless a specific, tested reason requires it.
- `kaggle kernels output` downloads **everything** present in
  `/kaggle/working` at exit, including an entire cloned git repository's
  `.git` internals if one wasn't cleaned up. The notebook must copy real
  outputs to a small dedicated folder and delete large working directories
  before exiting, or output retrieval will be slow and fragile on any
  imperfect connection.
- Status-check text must never be trusted with a naive substring check.
  `NameResolutionError` contains the substring "error"; a local network
  failure must not be classified the same as
  `KernelWorkerStatus.ERROR`/`FAILED` from Kaggle itself.
- The installed `kaggle` CLI version rejects `-d` on `datasets delete`;
  the working syntax is positional (`kaggle datasets delete <owner>/<slug>
  --yes`), matching every other command's calling convention.
- Kaggle provides no reliable API to force-stop an arbitrary running
  session. The one-shot "read a job, generate, exit" pattern exists
  specifically to avoid ever needing one.
- Multi-account rotation must persist *which account owns an in-flight run*
  (not just "is something running") so a backend restart resumes watching
  the correct run instead of rotating accounts and starting a duplicate.

## 3. Corrections to the Chief Engineer's assumptions

1. **"Inspect the existing repository"** — there isn't one in the sense the
   spec assumes. Chunk 0 below must first assemble the validated scripts and
   notebook cell source into an actual package structure. Everything after
   that proceeds against a real repository.
2. **Resolving Section 32 (VideoGenerationPort vs. ComputeExecutionPort
   decomposition):** the current implementation does *not* cleanly separate
   "compute" from "generation" — Wan2GP loads weights and runs inference
   inside the same Kaggle process that also *is* the compute environment.
   What genuinely varies today is *which Kaggle account/notebook instance*
   runs, not "which compute provider." Decision: `Wan2GPVideoGenerationAdapter`
   (implements `VideoGenerationPort`) depends on `ComputeExecutionPort`, and
   `KaggleComputeAdapter` implements that port, internally owning account
   rotation as a resource-selection detail (per the Chief Engineer's own
   Section 6 distinction). This matches the spec's first example shape
   exactly and is why a future hosted-API provider (e.g. Veo) can implement
   `VideoGenerationPort` directly without ever touching
   `ComputeExecutionPort` — it doesn't need one.
3. **Resolving Section 33 (provider selection boundary):** a single
   configuration value at the composition root (e.g.
   `GENERATION_PROVIDER=wan2gp_kaggle`) selects which concrete
   `VideoGenerationPort` implementation gets wired up. No scheduler, no
   capability-scoring logic yet — explicitly deferred per the spec's own
   instruction not to prematurely optimize.

## 4. Target architecture

```
Client (frontend / curl / future agentic caller)
        │  HTTP
        ▼
FastAPI (api/)
        │  calls
        ▼
Application use cases (application/)
        │  invoke
        ▼
Ports (application/ports.py — Protocols only)
   ├── VideoGenerationPort
   ├── ComputeExecutionPort
   ├── ArtifactStoragePort
   └── JobRepositoryPort
        │  implemented by
        ▼
Adapters (infrastructure/)
   ├── Wan2GPVideoGenerationAdapter  ──depends on──> KaggleComputeAdapter
   ├── LocalArtifactStorageAdapter
   └── SqliteJobRepository / InMemoryJobRepository
        │  talk to
        ▼
External systems: Kaggle CLI/API, the Kaggle notebook, local disk
```

## 5. Module boundaries

- **`api/`** — FastAPI app, routes, request/response schemas, dependency
  wiring (composition root lives here), HTTP error translation.
- **`application/`** — use cases, ports (as `Protocol` classes), DTOs,
  application-level exceptions. No use case may import anything from
  `infrastructure/`.
- **`domain/`** — `GenerationJob` (with lifecycle), `VideoGenerationRequest`,
  `ArtifactReference`, `GenerationResult`, `GenerationError`, enums. Zero
  third-party imports.
- **`infrastructure/generation/wan2gp/`** — `Wan2GPVideoGenerationAdapter`.
- **`infrastructure/compute/kaggle/`** — `KaggleComputeAdapter`, account
  rotation, the low-level `kaggle` CLI wrapper, and a versioned copy of the
  notebook's own cell source (see Section 15).
- **`infrastructure/storage/local/`** — `LocalArtifactStorageAdapter`.
- **`infrastructure/persistence/`** — `JobRepositoryPort` implementations.
- **`AI_state/`** — the docs-driven memory system (Section 17). Not code,
  but a first-class deliverable of every chunk.

## 6. Port definitions

**`VideoGenerationPort`**
- Purpose: request generation of a video clip without knowing which model
  or provider fulfills it.
- Caller: application use cases only.
- `submit(request: VideoGenerationRequest) -> GenerationJobRef`
- `get_status(job_ref) -> JobStatus`
- `get_result(job_ref) -> GenerationResult` (only valid once `SUCCEEDED`)
- `get_capabilities() -> ProviderCapabilities`
- Must NOT know: Kaggle, Wan2GP, Gradio, any vendor SDK.

**`ComputeExecutionPort`**
- Purpose: execute a workload somewhere, independent of what the workload
  does. Only generation adapters that genuinely need a separate execution
  environment depend on this — a hosted-API adapter never does.
- `submit(workload: ComputeWorkload) -> ComputeJobRef`
- `get_status(job_ref) -> ComputeJobStatus` — MUST distinguish
  `UNKNOWN_NETWORK_ERROR` (local connectivity problem, safe to retry) from
  `FAILED` (the provider genuinely reported failure) as **separate enum
  values**, not overloaded strings. This is the concrete fix for the bug in
  Section 2.
- `get_result(job_ref) -> list[ArtifactReference]`
- Must NOT know: application/domain concepts like "video" or "prompt."

**`ArtifactStoragePort`**
- Purpose: durable or intermediate storage of media artifacts, referenced
  by `ArtifactReference`, never by raw filesystem path outside the adapter
  that produced them.
- `store(local_path, metadata) -> ArtifactReference`
- `retrieve(ref) -> local path or stream`
- `exists(ref) -> bool`

**`JobRepositoryPort`**
- Purpose: persist `GenerationJob` records, including enough external
  correlation data (which account, which provider job ref) to *resume*
  tracking an in-flight job after a process restart — this is the concrete
  mechanism behind Section 22's resumability requirement.
- `save(job)`, `get(job_id)`, `find_in_flight() -> list[GenerationJob]`
  (used at startup to resume anything still running).

## 7. Adapter definitions

| Adapter | Implements | External system | Notes |
|---|---|---|---|
| `Wan2GPVideoGenerationAdapter` | `VideoGenerationPort` | (via `ComputeExecutionPort`) | Translates `VideoGenerationRequest` into the job-request JSON shape the notebook already expects; translates the notebook's output filename/status text back into `GenerationResult`. |
| `KaggleComputeAdapter` | `ComputeExecutionPort` | `kaggle` CLI, the notebook, Kaggle Datasets | Owns account rotation internally (a resource pool, not a port). Implements the docker-image-pin removal, dual-metadata-patch, network-vs-failure disambiguation, and output-folder cleanup behaviors from Section 2 as tested, documented code — not ad hoc script logic. |
| `LocalArtifactStorageAdapter` | `ArtifactStoragePort` | local disk | Wraps today's "download folder" behavior. |
| `SqliteJobRepository` (or file-backed) | `JobRepositoryPort` | local SQLite/JSON file | Must survive a process restart — this is what makes resumability real rather than in-memory-only. |

## 8. Dependency rules

- `domain/` → standard library only.
- `application/` → `domain/` and `application/ports.py` only. Never
  `fastapi`, `kaggle`, `gradio`, any vendor SDK.
- `infrastructure/*` → may depend on `application/` (to implement its
  ports) and on whatever external library/CLI it wraps.
- `api/` → depends on `application/` use cases only, never directly on
  `infrastructure/` concrete classes (those are wired at the composition
  root and injected).

## 9. Data/contracts (domain)

- `VideoGenerationRequest`: `request_id`, `prompt`, `negative_prompt?`,
  `duration_seconds`, `resolution?`, `aspect_ratio?`, `seed?`,
  `start_frame: ArtifactReference?`, `end_frame: ArtifactReference?`,
  `provider_preference?` (a hint, not a hard requirement the domain
  enforces), `idempotency_key?`.
- `GenerationJob`: `job_id`, `request`, `status` (enum, see Section 12),
  `external_ref?` (opaque, e.g. which Kaggle account + notebook version —
  stored, never interpreted by the domain), `created_at`, `updated_at`,
  `result: GenerationResult?`, `error: GenerationError?`.
- `ArtifactReference`: `artifact_id`, `storage_kind` (enum: LOCAL, and
  future KAGGLE_OUTPUT/GDRIVE/OBJECT_STORAGE), `location` (opaque string).
- `GenerationResult`: `output_artifacts: list[ArtifactReference]`,
  `duration_seconds_actual`, `provider_name`, `generated_at`.
- `ProviderCapabilities`: the capability list already established in the
  earlier LTX module work (TEXT_TO_VIDEO, IMAGE_TO_VIDEO via start/end
  frame, SEED_CONTROL, DURATION_CONTROL, etc.) — reuse that enum rather
  than reinventing it.

## 10. FastAPI boundary

Routes (thin — map HTTP ⇄ application DTOs only, no business logic):
- `GET /health` — liveness/readiness.
- `POST /video-generations` — body: prompt + optional params → 201 +
  job id/status.
- `GET /video-generations/{id}` — current status.
- `GET /video-generations/{id}/result` — 200 + artifact info once
  succeeded, 409 if not yet finished.

Error mapping: validation → 400; capability unsupported → 422; not found →
404; provider/infrastructure failure → 502/503; never leak a raw
`kaggle`/subprocess exception message into a response body.

## 11. Configuration

Single `config.py`, loaded from environment variables:
`GENERATION_PROVIDER`, `KAGGLE_ACCOUNTS_DIR` (defaults to
`~/.kaggle/accounts/`), `ARTIFACT_STORAGE_DIR`, `JOB_DB_PATH`. Never
hardcode a Kaggle username, account count, or channel-specific value
anywhere outside this file and the account credential files themselves.

## 12. Job lifecycle

States: `REQUESTED → QUEUED → RUNNING → SUCCEEDED`, or
`RUNNING → FAILED`. `UNKNOWN_RECOVERING` is a real, necessary state — used
when the application restarts and finds an in-flight job via
`JobRepositoryPort.find_in_flight()` but hasn't yet re-confirmed its status
with the provider. No `CANCELLED` state is promised, per the Chief
Engineer's own instruction — Kaggle has no reliable stop mechanism.

**Network-interruption rule, made concrete:** the transition into `FAILED`
may only be triggered by a provider explicitly reporting failure
(`ComputeJobStatus.FAILED` from the adapter). A local connectivity
exception while polling must leave the job's stored status unchanged and
simply be retried — this is the exact, previously-real bug this rule exists
to prevent.

## 13. Artifact handling

`ArtifactReference` is the only thing the domain/application ever holds for
a piece of media — never a bare path. `LocalArtifactStorageAdapter` is the
only implementation for this module; the reference format is designed so a
future `GoogleDriveStorageAdapter` or object-storage adapter can be swapped
in without changing any `ArtifactReference` already stored.

## 14. Provider selection

Composition root reads `GENERATION_PROVIDER` once at startup and wires the
matching concrete `VideoGenerationPort` implementation. No conditional
branching on provider name anywhere else in the codebase.

## 15. Current Kaggle integration mapping

| Existing script/behavior | New home |
|---|---|
| `kaggle_accounts.get_next_account()` | `infrastructure/compute/kaggle/accounts.py` — internal to `KaggleComputeAdapter`, not exposed as a port. |
| `kaggle_notebook_control.push_job_request/start_notebook/wait_for_completion/fetch_outputs/delete_dataset` | Become private methods of `KaggleComputeAdapter` implementing `submit()/get_status()/get_result()`; `wait_for_completion`'s polling loop is NOT re-implemented inside the adapter's `get_status()` — `get_status()` does one check and returns, matching the port's non-blocking contract; polling belongs to whoever calls it repeatedly (a background task or the API's own status endpoint being called repeatedly). |
| `run_backend_job_cycle.py`'s orchestration | Becomes `RequestVideoGeneration` / `GetGenerationStatus` / `GetGenerationResult` use cases, invoked by FastAPI instead of a `__main__` script. |
| `active_run_state.json` | Superseded by `JobRepositoryPort.find_in_flight()` — the same resumability principle, now backed by the real job repository instead of a bespoke file. |
| The notebook's own cells (Steps 1–4, headless step 4) | Copied as versioned plain-text files under `infrastructure/compute/kaggle/notebook_source/` — this becomes the single source of truth Gemini and future sessions read, instead of "whatever's currently saved on kaggle.com." `KaggleComputeAdapter` is responsible for keeping the live Kaggle notebook in sync with this source (push it) rather than assuming they match. |
| The docker-image-pin fix, dual-metadata patch, network/failure disambiguation, output-folder cleanup, positional `datasets delete` syntax | Preserved verbatim as adapter behavior, each with its own test (Section 16) that would have caught the original bug. |

## 16. Testing architecture

- **Domain:** valid/invalid `VideoGenerationRequest`s, `GenerationJob`
  transition legality (including that only a genuine provider-reported
  failure reaches `FAILED`).
- **Application:** use cases against fake `VideoGenerationPort`/
  `JobRepositoryPort` — prove none of it needs Kaggle or Wan2GP to run.
- **`KaggleComputeAdapter`:** mock the `kaggle` CLI subprocess calls;
  specifically test: docker_image gets stripped, both metadata layers get
  patched, a `NameResolutionError`-style stdout does NOT produce a `FAILED`
  status, a genuine `KernelWorkerStatus.ERROR` does, `datasets delete` uses
  positional syntax.
- **FastAPI:** request validation, success path, status/result retrieval,
  error mapping, dependency wiring.
- **Architecture tests:** assert `domain/` and `application/` import
  nothing from `fastapi`, `kaggle`, `gradio`, or any adapter package.
- Real Kaggle generation stays a manual/opt-in integration test, never part
  of the default suite.

## 17. Documentation plan — the docs-driven AI state system

Create `AI_state/` at the repo root with these files, all Markdown,
**updated as part of every chunk that changes anything they describe:**

- **`SESSION_HANDOFF.md`** — the only file a fresh session must read first.
  Contains: current chunk in progress or next chunk to start, one paragraph
  of context, and pointers to the other files. Kept short on purpose.
- **`CURRENT_STATE.md`** — what's implemented right now: modules that
  exist, ports/adapters that are real vs. stubbed, what currently passes
  end-to-end.
- **`PROGRESS.md`** — append-only, dated log, one entry per completed
  chunk: what was built, what tests were added, what deviated from spec
  and why.
- **`ARCHITECTURE_STATE.md`** — the live module/port/adapter map (kept in
  sync with Sections 5–7 as the real code evolves past this initial spec).
- **`TEST_STATE.md`** — what's tested, known gaps, whether the manual
  Kaggle integration test has actually been run recently.
- **`KNOWN_ISSUES.md`** — starts as a copy of Section 2's landmine list;
  grows with anything new discovered; a fixed issue is marked fixed with
  the chunk/date, never deleted (history matters more than tidiness here).

Each chunk in Section 19 lists exactly which of these files it must touch —
none of them are optional busywork; skipping them is the single fastest way
to make the next session re-discover bugs already fixed once.

## 18. Gemini coding instructions

- Read `AI_state/SESSION_HANDOFF.md` before starting any chunk.
- Inspect what actually exists before assuming — the scripts described in
  Section 2 are real behavior to preserve, not a rough sketch to discard.
- Never bypass a port. Never let `application/` or `domain/` import an
  infrastructure package directly.
- Never put business logic in a FastAPI route function.
- Never hardcode a Kaggle username, account count, or channel value.
- Never classify a local/transport exception as a definitive remote
  failure — always distinguish "unknown, retry" from "confirmed failed."
- Never introduce a universal cross-provider "LoRA API" — LoRA stays a
  provider-specific, undecided future concern per Section 12 of the spec.
- Write tests in the same chunk as the code, not a later chunk.
- Update `AI_state/*.md` in the same chunk as the code change.
- Run the relevant test suite after every chunk and report the result,
  including failures — do not silently work around a failing test by
  changing the test's expectations to match broken code.
- If a chunk's instructions conflict with what inspection reveals, stop and
  report the conflict rather than guessing.

## 19. Gemini implementation chunks

### CHUNK 0 — Repository Assembly & AI State Bootstrap
**Objective:** Turn the scattered validated scripts and notebook cell text into a real, importable repository, and stand up `AI_state/`.
**Preconditions:** None — this is the starting point.
**Files/modules affected:** Create the full directory skeleton from Section 5; create `AI_state/` with all six files (initial content: a snapshot of this document's Sections 2 and 15).
**Implementation instructions:** You must place the Human Project Owner's current backend scripts and Kaggle notebook cell source into the paths named in Section 15's table, unmodified in behavior at this stage — this chunk is organizational, not a rewrite.
**Constraints:** Do not refactor behavior yet. Do not skip copying the notebook's own cell source — a repository without it is incomplete per Section 2.
**Tests:** A smoke test that every listed file exists and every Python file at least imports without error.
**Documentation:** `AI_state/CURRENT_STATE.md` states "pre-refactor, behavior-preserving snapshot only."
**Verification:** `python -c "import <each new package>"` succeeds.
**Completion criteria:** Repository skeleton exists; `AI_state/` exists and is accurate; nothing has changed behaviorally yet.

### CHUNK 1 — Domain Layer
**Objective:** Implement `domain/` per Section 9.
**Preconditions:** Chunk 0.
**Files/modules affected:** `domain/entities.py`, `value_objects.py`, `enums.py`, `exceptions.py`.
**Implementation instructions:** Implement every type in Section 9 plus the job lifecycle from Section 12, including the `UNKNOWN_RECOVERING` state and the rule that only an explicit provider-failure signal may cause a `FAILED` transition.
**Constraints:** Zero third-party imports in this package.
**Tests:** Every valid/invalid request case; every legal/illegal lifecycle transition, explicitly including a test proving a generic exception object cannot trigger `FAILED`.
**Documentation:** `docs/domain-model.md`; update `AI_state/ARCHITECTURE_STATE.md` and `PROGRESS.md`.
**Verification:** Domain test suite green; architecture check shows zero external imports.
**Completion criteria:** All Section 9 types exist and are fully tested.

### CHUNK 2 — Ports
**Objective:** Define all four ports from Section 6 as `Protocol` classes.
**Preconditions:** Chunk 1.
**Files/modules affected:** `application/ports.py`.
**Implementation instructions:** Implement exactly the method signatures in Section 6, including `ComputeJobStatus` having distinct `FAILED` and `UNKNOWN_NETWORK_ERROR` values (not a shared string).
**Constraints:** No implementation logic, no adapter imports.
**Tests:** Type-conformance checks only.
**Documentation:** `docs/ports.md`; update `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** All ports compile and are fully typed.

### CHUNK 3 — Fakes & Contract Tests
**Objective:** Build fakes for every port and a shared contract-test suite any real adapter must also pass.
**Preconditions:** Chunk 2.
**Files/modules affected:** `infrastructure/*/fakes.py`, `tests/contract/`.
**Implementation instructions:** Fakes must be able to simulate a provider-reported failure and a network-unknown state as distinct outcomes, so the contract suite can prove real adapters handle both correctly later.
**Tests:** The contract suite itself, run against the fakes.
**Documentation:** Update `AI_state/TEST_STATE.md`.
**Completion criteria:** Contract suite passes against all fakes.

### CHUNK 4 — KaggleComputeAdapter
**Objective:** Implement `ComputeExecutionPort` for real, migrating the validated behavior from Section 2/15 with each fix preserved and tested.
**Preconditions:** Chunk 3.
**Files/modules affected:** `infrastructure/compute/kaggle/adapter.py`, `accounts.py`, `notebook_source/*`.
**Implementation instructions:** You must implement, as separately testable behaviors: (a) stripping any pinned `docker_image` before triggering a run, (b) patching both `kernel-metadata.json` and the `.ipynb`'s own embedded `metadata.kaggle` block, (c) classifying status text into `RUNNING`/`SUCCEEDED`/`FAILED`/`UNKNOWN_NETWORK_ERROR` using explicit markers, never a bare `"error" in text` check, (d) copying real outputs to a clean folder and deleting large working directories before the notebook exits, (e) using positional syntax for `kaggle datasets delete`, (f) account rotation that persists which account owns an in-flight job.
**Constraints:** This adapter is the only place `kaggle` CLI calls or notebook-source details may appear.
**Tests:** One test per behavior in (a)–(f) above, each using a mocked `kaggle` CLI. Include a test that replays the exact `NameResolutionError` text from the real incident and asserts it does NOT produce `FAILED`.
**Documentation:** `docs/adapters/kaggle-compute.md`; update `AI_state/KNOWN_ISSUES.md` marking each landmine "fixed here, regression-tested."
**Verification:** Full adapter test suite green with no network access.
**Completion criteria:** All six behaviors implemented and independently tested.

### CHUNK 5 — Wan2GPVideoGenerationAdapter
**Objective:** Implement `VideoGenerationPort`, depending on `ComputeExecutionPort`.
**Preconditions:** Chunk 4.
**Files/modules affected:** `infrastructure/generation/wan2gp/adapter.py`.
**Implementation instructions:** Translate `VideoGenerationRequest` (including `start_frame`/`end_frame` `ArtifactReference`s) into the job-request JSON shape the notebook already reads; translate the notebook's completion output into `GenerationResult`. Declare capabilities matching what the notebook actually supports today (text-to-video, single start/end frame image conditioning, seed control) — do not overclaim.
**Constraints:** No direct `kaggle` CLI calls here — everything compute-related goes through the injected `ComputeExecutionPort`.
**Tests:** Translation tests (request → workload, result → `GenerationResult`) using the Chunk 3 fake compute port.
**Documentation:** `docs/adapters/wan2gp-generation.md`; update `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** Adapter passes the Chunk 3 `VideoGenerationPort` contract suite using the fake compute adapter.

### CHUNK 6 — Application Use Cases
**Objective:** Implement `RequestVideoGeneration`, `GetGenerationStatus`, `GetGenerationResult`.
**Preconditions:** Chunk 5.
**Files/modules affected:** `application/use_cases.py`, `dto.py`.
**Implementation instructions:** `RequestVideoGeneration` persists the job via `JobRepositoryPort` before calling `VideoGenerationPort.submit()`, so a crash between those two steps is recoverable. Add a startup routine (used by Chunk 8's composition root) that calls `find_in_flight()` and reconciles each job's real status — this is where `UNKNOWN_RECOVERING` gets resolved.
**Constraints:** No imports from `infrastructure/`.
**Tests:** Against fakes only; explicitly test the persist-before-submit ordering and the startup reconciliation path.
**Documentation:** `docs/use-cases.md`; update `AI_state/PROGRESS.md`.
**Completion criteria:** All three use cases pass tests using only fakes.

### CHUNK 7 — Local Storage & Job Repository
**Objective:** Implement `LocalArtifactStorageAdapter` and a durable (file/SQLite-backed) `JobRepositoryPort`.
**Preconditions:** Chunk 6.
**Files/modules affected:** `infrastructure/storage/local/adapter.py`, `infrastructure/persistence/*.py`.
**Implementation instructions:** The job repository must survive a process restart — this replaces `active_run_state.json`'s role with something queryable (`find_in_flight()`), not just a single-record file.
**Tests:** Contract suite from Chunk 3; a restart-simulation test (save a job, create a fresh repository instance pointed at the same file/DB, confirm the job is still found via `find_in_flight()`).
**Documentation:** Update `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** Both adapters pass their contract suites; restart-simulation test passes.

### CHUNK 8 — FastAPI Delivery Layer
**Objective:** Implement the API from Section 10 plus the composition root.
**Preconditions:** Chunk 7.
**Files/modules affected:** `api/main.py`, `routers/generation.py`, `schemas.py`, `dependencies.py`, `error_handlers.py`, `config.py`.
**Implementation instructions:** Composition root reads `GENERATION_PROVIDER` and other config from `config.py`, constructs the real adapters, injects them into use cases, and runs the startup reconciliation from Chunk 6 before accepting traffic.
**Constraints:** No business logic in route functions.
**Tests:** Per Section 16's FastAPI test list.
**Documentation:** `docs/api.md`; update `AI_state/CURRENT_STATE.md` to say the API boundary is live.
**Completion criteria:** All API tests pass; app starts with real config.

### CHUNK 9 — Architecture Tests & Boundary Enforcement
**Objective:** Automate the dependency rules from Section 8.
**Preconditions:** Chunk 8.
**Files/modules affected:** `tests/architecture/`.
**Implementation instructions:** Assert zero imports of `fastapi`/`kaggle`/`gradio`/adapter packages from `domain/`/`application/`.
**Tests:** The assertions themselves.
**Documentation:** Update `AI_state/TEST_STATE.md`.
**Completion criteria:** Architecture suite fails on a deliberately introduced violation (verify this once, then revert).

### CHUNK 10 — Documentation & AI State Finalization
**Objective:** Bring all `docs/*.md` and `AI_state/*.md` fully up to date with the real, finished implementation.
**Preconditions:** Chunk 9.
**Implementation instructions:** Every port and adapter documented per the Chief Engineer's Section 27 template (purpose, responsibilities, non-responsibilities, interface, failure behavior, configuration).
**Documentation:** This chunk IS the documentation update.
**Completion criteria:** A fresh reader of `AI_state/SESSION_HANDOFF.md` plus `docs/` can explain the whole system without this conversation.

### CHUNK 11 — End-to-End Manual Verification
**Objective:** Prove the full chain in Section 4 works with a real generation.
**Preconditions:** Chunk 10.
**Implementation instructions:** Run the manual test procedure in Section 20 for real.
**Constraints:** Do not claim this passed unless actually executed against real Kaggle.
**Documentation:** Record the real result (success/failure, timing) in `AI_state/PROGRESS.md` and `TEST_STATE.md`.
**Completion criteria:** A real video generated through the new API boundary, downloaded, and confirmed playable.

## 20. Manual testing guide

1. Set `KAGGLE_ACCOUNTS_DIR`, `GENERATION_PROVIDER=wan2gp_kaggle`, and other
   config env vars.
2. Start the API: `uvicorn api.main:app`.
3. `curl -X POST /video-generations -d '{"prompt": "..."}'` → note the
   returned job id.
4. Poll `GET /video-generations/{id}` every ~30s.
5. Watch the Kaggle notebook's own log page in a browser in parallel —
   confirm `Detected GPUs: 2` and the job-request being read.
6. Once status is `SUCCEEDED`, call `GET /video-generations/{id}/result` and
   confirm an `ArtifactReference` is returned.
7. Retrieve the actual file via the local storage adapter's path and play it.
8. **Interruption test (required, not optional):** kill the API process
   mid-poll, restart it, and confirm the reconciliation logic from Chunk 6
   correctly finds and resumes tracking the still-running job instead of
   losing it or starting a duplicate.
9. Failure looks like: an HTTP error with a clean message, never a raw
   traceback or a job silently disappearing.

## 21. Acceptance checklist

- [ ] Real Wan2GP/Kaggle generation still works, now through the API.
- [ ] `domain/`/`application/` contain zero Kaggle/Wan2GP/FastAPI imports.
- [ ] A network blip during polling does not mark a job `FAILED`.
- [ ] Restarting the API mid-job resumes tracking without duplicating work.
- [ ] `AI_state/SESSION_HANDOFF.md` alone is enough to resume work cold.
- [ ] Every port has at least one fake and passes the shared contract suite.
- [ ] No hardcoded credentials, usernames, or channel-specific values exist.

## 22. Future extension points

- A `VeoVideoGenerationAdapter` implementing `VideoGenerationPort` directly
  (no `ComputeExecutionPort` needed, per Section 3's resolved decision).
- A workflow layer that extracts a last frame as an `ArtifactReference` and
  feeds it into the next `VideoGenerationRequest.start_frame` — the current
  contracts already make this possible without a DAG engine.
- `GoogleDriveStorageAdapter` / object-storage adapter implementing
  `ArtifactStoragePort`.
- A channel-configuration layer that supplies `provider_preference` and
  future LoRA/style parameters without the core ever branching on channel
  identity.

## 23. Known limitations / intentionally deferred

- No cancellation is promised — Kaggle offers no reliable stop mechanism.
- GPU quota availability varies by account and is not modeled or predicted.
- The Kaggle notebook's docker image is left at Kaggle's current default
  (unpinned) per the validated fix — if Kaggle's default image changes
  behavior in the future, this is a real risk to re-test, not a solved
  problem forever.
- Only one in-flight generation per account is assumed; true concurrency
  across accounts is possible but not yet orchestrated.
- LoRA, character identity, multi-channel configuration, publishing
  automation, and workflow/DAG orchestration are explicitly out of scope
  for this module, per the Chief Engineer's Section 35.
