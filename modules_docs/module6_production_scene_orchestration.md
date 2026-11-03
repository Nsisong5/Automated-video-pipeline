# Module 6 — Production/Episode/Scene Domain & Sequential Orchestration

Prepared by: Claude (Technical Specification Engineer)
For: Gemini CLI | Human Project Owner: Wilfred Jasper
Depends on: Module 4 (verified), Module 5 (clean single-artifact retrieval)

## 1. Module purpose
Move the system from "generate one video" to "generate an episode composed
of manually authored, sequentially-generated scenes," while keeping video
generation itself a pure capability that knows nothing about episodes.

## 2. Responsibilities
- Domain concepts: `Production`, `Scene`, explicit scene ordering.
- An application-level orchestration service that generates scenes one at
  a time, persists each result, and is resumable across restarts.
- Persistence of production/scene state.
- Minimal API surface to create, start, and observe a production.

## 3. Non-responsibilities
Does not know how to extract frames or assemble video (Module 7 — a
`Production`'s scenes simply end up as an ordered list of
`ArtifactReference`s; what happens to them next is Module 7's job). Does
not implement channel-specific behavior. Does not implement parallel
execution, a DAG engine, or automated scene authoring.

## 4. Architecture — resolved investigation answers

**(A) Where Production/Scene live:** `domain/`. They are core business
concepts with real invariants (explicit ordering, one owning production per
scene, valid state transitions) — the same category as `GenerationJob` in
Module 4, not infrastructure and not merely DTOs.

**(B) Artifact lifecycle across this module:**
```
Orchestration triggers Scene N's generation
   → VideoGenerationPort.submit(request built from Scene N)
   → (Module 4/5 path) → GenerationResult with one ArtifactReference
   → orchestration calls ArtifactStoragePort.store(), placing it under
     productions/<production_id>/scenes/<scene_id>/video.mp4
   → Scene.generated_artifact = the NEW stable reference from storage
     (not the transient one the generation adapter returned)
   → orchestration advances to Scene N+1
```
Note the deliberate re-reference: the generation adapter's `ArtifactReference`
is transient (may point at a temp download location); the *stored* reference
is what `Scene` actually keeps, so storage location can change providers
later without touching `Scene`.

**(F) Sequential coordination — the "lazy tick" pattern:** no background
worker or scheduler is introduced (explicitly out of scope). Instead:
`GetProductionStatus` (and a dedicated internal reconciliation path) does
real work on every call — it checks the currently-active scene's real job
status via `VideoGenerationPort.get_status()`; if that scene just finished,
it stores the artifact, marks the scene done, and **starts the next scene's
generation right there** before returning the response. This means simply
polling status (exactly like the existing Kaggle job polling already does)
is what drives the whole production forward — no separate infrastructure
needed, and it's naturally resumable: after a restart, the very next status
check (or a startup reconciliation pass, reusing Module 4's
`find_in_flight()` pattern) picks up exactly where things left off.

**(I) Persistence:** `Production` and its `Scene`s are persisted as **one
aggregate** — a `Scene` is never queried independently of its owning
`Production`, so a single `ProductionRepositoryPort` (mirroring
`JobRepositoryPort`'s shape) is simpler and correct: `save(production)`,
`get(production_id)`, `find_in_flight()`.

**(J) API:** exactly the five endpoints the Chief Engineer suggested,
confirmed as sufficient for manual operation — see Section 10.

## 5. Public interfaces (new/changed)

No new *generation* port — `VideoGenerationPort` is reused unchanged, one
call per scene. One new port:

**`ProductionRepositoryPort`**
- Purpose: persist production/scene state durably, enabling resumability.
- `save(production: Production) -> None`
- `get(production_id) -> Production | None`
- `find_in_flight() -> list[Production]`

## 6. Adapters
`SqliteProductionRepository` (or file-backed, matching whatever Module 4's
`JobRepositoryPort` implementation used — reuse the same persistence
technology, don't introduce a second one without reason).

## 7. Data models

- **`Production`**: `production_id`, `title`, `channel_id` (a plain string
  identifier — no channel-specific logic anywhere near this, just a tag),
  `status` (enum: `CREATED`, `RUNNING`, `SUCCEEDED`, `FAILED`), `scenes:
  list[Scene]` (order = list order, explicit and authoritative — never
  inferred from IDs or filesystem), `created_at`, `updated_at`.
- **`Scene`**: `scene_id`, `production_id`, `sequence_index` (explicit
  integer, the real ordering authority), `generation_request:
  VideoGenerationRequest` (reused from Module 4 as-is — no duplicate
  generation-config concept), `status` (enum: `NOT_STARTED`, `RUNNING`,
  `SUCCEEDED`, `FAILED`), `job_ref` (opaque, correlates to the underlying
  `VideoGenerationPort` job), `generated_artifact: ArtifactReference?`.

## 8. Communication flow
```
POST /productions  → creates Production (status CREATED) with N scenes,
                      sequence_index 0..N-1, each an unsubmitted
                      VideoGenerationRequest
POST /productions/{id}/start
   → status → RUNNING
   → submits Scene[0]'s generation via VideoGenerationPort
   → persists
GET /productions/{id}/status  (called repeatedly — this IS the driver)
   → checks Scene[current].status via VideoGenerationPort.get_status()
   → on success: store artifact, mark scene SUCCEEDED, submit next scene
   → on all scenes SUCCEEDED: Production → SUCCEEDED
   → returns current per-scene progress
GET /productions/{id}/artifact  → per-scene artifacts (final assembled
                                   episode artifact belongs to Module 7)
```

## 9. Persistence
`Production` (with embedded `Scene`s) persisted as one JSON-serializable
aggregate via `ProductionRepositoryPort`, using the same storage technology
Module 4 chose for `JobRepositoryPort`.

## 10. Artifact lifecycle
Covered in Section 4(B). Storage path convention:
`productions/<production_id>/scenes/<scene_id>/video.mp4` (or whatever
`LocalArtifactStorageAdapter`'s existing path convention is — reuse it,
don't invent a second one).

## 11. Testing
- **Domain**: valid/invalid `Production`/`Scene`, explicit-order invariant
  (rejecting duplicate/missing sequence indices), state transition legality.
- **Application** (using Module 4's fakes plus a fake
  `ProductionRepositoryPort`): prove the full 5-scene sequential flow works
  with zero real Kaggle/Wan2GP calls; prove a simulated restart mid-production
  (fresh orchestration instance, same persisted state) resumes at the
  correct scene rather than restarting from Scene 0 or losing track.
- **FastAPI**: creation, start, status progression, artifact retrieval,
  validation errors.

## 12. Manual testing — first multi-scene episode
Exactly the Chief Engineer's Section 30 procedure: create a 5-scene
production via the API, start it, poll status repeatedly, confirm each
scene generates in order with no duplicate/misplaced artifacts, confirm all
five artifacts exist under the correct per-scene paths. (Final assembly
into one episode file is Module 7 — this module's manual test stops at
"five correctly-stored, correctly-ordered scene clips.")

## 13. Extension guide
A future automated scene-planning capability produces the same
`Production`/`Scene` structures this module accepts manually — it becomes
a new caller of `POST /productions`, not a change to this module. A future
parallel-execution optimization would replace the "lazy tick" advance logic
without changing `Production`/`Scene`'s shape.

## 14. Gemini implementation chunks

### CHUNK 6.0 — Prerequisite Gate
**Objective:** Confirm Module 5 is complete (single canonical artifact retrieval verified) before starting.
**Manual check:** Human Project Owner confirms.

### CHUNK 6.1 — Domain: Production & Scene
**Objective:** Implement `Production`, `Scene`, their enums and invariants.
**Files/modules affected:** `domain/production.py` (or wherever Module 4's domain package convention puts entities).
**Tests:** All invariants from Section 11's domain list.
**Manual check:** None (pure domain logic).
**Documentation:** `docs/domain-model.md` updated; `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** Full domain test coverage green.

### CHUNK 6.2 — ProductionRepositoryPort + Persistence Adapter
**Objective:** Implement the port and a durable adapter.
**Tests:** Contract test plus the restart-simulation test (save, fresh instance, `find_in_flight()` still finds it).
**Manual check:** None (fully testable via fakes/real file).
**Documentation:** `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** Restart-simulation test passes.

### CHUNK 6.3 — Application: Sequential Orchestration ("lazy tick")
**Objective:** Implement `CreateProduction`, `StartProduction`, `GetProductionStatus` (the tick logic lives here), using Module 4's `VideoGenerationPort`/`ArtifactStoragePort` and this module's `ProductionRepositoryPort`.
**Constraints:** No direct infrastructure imports; use cases depend only on ports.
**Tests:** Full 5-scene sequential flow against fakes; restart-mid-production resumption test.
**Manual check:** None yet (API not wired until Chunk 6.5) — covered by automated tests only.
**Documentation:** `docs/use-cases.md`; `AI_state/PROGRESS.md`.
**Completion criteria:** Sequential flow and resumption tests both green.

### CHUNK 6.4 — Storage Path Convention for Scenes
**Objective:** Extend `LocalArtifactStorageAdapter` usage so scene artifacts land at `productions/<id>/scenes/<id>/video.mp4`.
**Constraints:** Reuse the existing storage adapter's mechanism — do not create a second storage abstraction.
**Tests:** Confirm correct path construction and that re-storing doesn't collide across productions.
**Manual check:** Inspect the local filesystem after one test run; confirm the directory shape matches Section 4(B)/Section 10.

### CHUNK 6.5 — FastAPI: Production Endpoints
**Objective:** Implement the five endpoints from Section 8.
**Constraints:** No business logic in routes; existing single-video endpoints must remain untouched and working.
**Tests:** Per Section 11's FastAPI list.
**Manual check:** Run the actual manual test from Section 12 for real — five scenes, real generation, real ordering confirmed.
**Documentation:** `docs/api.md`; `AI_state/CURRENT_STATE.md`.
**Completion criteria:** Section 12's manual test passes for real, not simulated.

### CHUNK 6.6 — Documentation Finalization
**Objective:** Bring all Module 6 docs and `AI_state/*` fully current.
**Completion criteria:** A fresh reader understands Production/Scene orchestration without this spec.
