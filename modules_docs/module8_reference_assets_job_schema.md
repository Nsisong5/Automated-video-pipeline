# Module 8 — Reference Assets & Extended Job Schema

Prepared by: Claude (Technical Specification Engineer)
For: Gemini CLI (Implementation)
Depends on: Module 1 (application boundary), Module 5 (canonical artifact), Module 6 (Production/Scene orchestration), Module 7 (chaining/assembly)

---

## 0. How to use this document

- Read `AI_state/SESSION_HANDOFF.md` first.
- Execute **one chunk at a time**. After each chunk: run the tests, update `AI_state/*`, report, then **STOP and wait for approval**. Never start the next chunk on your own.
- Tests are written in the same chunk as the code. `AI_state/*` is updated in the same chunk as the code.
- If anything you find contradicts this document, stop and report the conflict. Do not guess.
- Paths in this document come from the specs. The real repository may differ (for example the generation adapter lives at `infrastructure/generation/ltx25/adapter.py`). Use the real paths, and say so in your report.
- Do not claim a manual check passed unless it was actually run.

---

## 1. Purpose

The Kaggle notebook is gaining the ability to create and use **reference assets** (for example a character or a vehicle that must look the same across scenes). Its job file changes shape. The backend must accept the new request shape, validate it, persist it, and deliver it to the notebook exactly as the notebook expects.

**Current symptom:** posting the new payload to the backend produces an unhandled error instead of a clean result. Chunk 0 finds out exactly where it fails.

**Scope boundary:** this module only changes how the job is described, validated, stored and delivered. It does not touch notebook internals, how reference images are generated, how `chain_from_previous` works (the notebook handles it; we only pass the flag through), or video assembly.

---

## 2. Which existing modules this touches

| Existing module | What it owns | What changes here |
|---|---|---|
| Module 6 — `Production`/`Scene` domain, `CreateProduction`/`StartProduction`, `POST /productions` | Production and scene model, creation flow, API input schema | Production gains `reference_assets`; scenes gain `reference_asset_ids` and an optional client `job_id`; the creation use case and the API schema accept the new body |
| Module 1 — `VideoGenerationRequest`, `VideoGenerationPort`, `ProviderCapabilities`, generation adapter (`ltx25`/Wan2GP) | Provider-neutral request, the port, translation to the notebook job shape | Request gains `reference_asset_ids`; the batch submit contract carries reference assets; a new capability is declared; the adapter emits the new notebook shape |
| Module 1/4 — `KaggleComputeAdapter` and `notebook_control.push_job_request` | Writes `jobs.json` into the Kaggle dataset | Writes the new two-key payload. **Only the payload content changes.** Do not change submission or error-handling behaviour here (a separate fix sequence owns that) |
| Module 5 — canonical artifact | `final_output/<job_id>.mp4` | **Not changed.** But the job id sent to the notebook now may be client-supplied, so the job-to-scene mapping must keep working (see Chunk 3) |
| Module 7 — chaining and assembly | `chain_from_previous`, frame extraction, assembly | **Not changed.** The flag is passed through exactly as today |

Dependency rules still apply: `domain/` uses the standard library only; `application/` never imports `infrastructure/`; `api/` never imports concrete adapters; only the generation adapter knows the notebook's JSON shape.

---

## 3. Contracts

### 3.1 Incoming API body (`POST /productions`)

Top level:

| Field | Required | Notes |
|---|---|---|
| `jobs` | yes | list, at least 1. Legacy alias: `scenes` (see decision D1) |
| `reference_assets` | no | list, default `[]` |
| `title` | no | default `"Untitled Production"` (decision D2) |
| `channel_id` | no | default `"default"` (decision D2) |

Each **job**:

| Field | Required | Notes |
|---|---|---|
| `prompt` | yes | non-empty string |
| `duration_seconds` | yes | same rule as today |
| `chain_from_previous` | no | bool, default `false`, same as today |
| `job_id` | no | client key; `^[A-Za-z0-9_-]{1,64}$`; unique within the production |
| `reference_asset_ids` | no | list of strings, default `[]`; each must match a declared `asset_id` |
| `aspect_ratio` | no | opaque string, passed through (decision D3) |
| `resolution` | no | opaque string, passed through (decision D3) |
| `seed` | no | integer |

Each **reference asset**:

| Field | Required | Notes |
|---|---|---|
| `asset_id` | yes | `^[A-Za-z0-9_-]{1,64}$`, unique within the production |
| `creation.method` | yes | `"generate"` or `"upload"` |
| `creation.prompt` | when method = generate | non-empty |
| `creation.negative_prompt` | no | string |
| `creation.aspect_ratio` | no | opaque string (note: a different vocabulary from the job-level `aspect_ratio`, e.g. `"16:9"` versus `"16:9 Landscape"`; never normalise either) |
| `creation.uploaded_image_ref` | when method = upload | string |
| `required` | no | bool; tri-state, see decision D6 |
| `name`, `category` | no | optional descriptive strings |

Unknown fields anywhere are **rejected** with a clear message naming the field path (decision D5).

### 3.2 Notebook-facing `jobs.json` shape (what the notebook reads)

```json
{
  "reference_assets": [ { "asset_id": "...", "required": true, "creation": { "method": "generate", "prompt": "...", "aspect_ratio": "16:9" } } ],
  "jobs": [ { "job_id": "...", "prompt": "...", "duration_seconds": 5, "chain_from_previous": false,
              "reference_asset_ids": ["..."], "aspect_ratio": "16:9 Landscape", "resolution": "...", "seed": 42 } ]
}
```

Rules: reference assets and job fields are emitted **verbatim as provided**; an absent optional field is **omitted** (never `null`, never a backend-invented default); both top-level keys are always present (`reference_assets` is `[]` when none). The full golden sample is in Appendix A.

### 3.3 Decisions already made (do not re-debate; report if one is unworkable)

- **D1.** Accept `jobs` (new) and `scenes` (legacy alias). Both normalise to the same internal structure. Sending both is a validation error.
- **D2.** `title` and `channel_id` become optional at the API boundary with the defaults above. The domain `Production` still always has both.
- **D3.** `aspect_ratio` and `resolution` are opaque pass-through strings. The labels (`"16:9 Landscape"`, `"Fast Preview (384p - ~1-2 min)"`) are notebook UI vocabulary leaking into our contract. We accept that for now, record it as a design debt in `AI_state/KNOWN_ISSUES.md`, and do **not** build a translation layer in this module.
- **D4.** `creation.method = "upload"` is accepted by the schema but rejected with a clean "not yet supported" error. Staging uploaded images to the notebook needs its own module.
- **D5.** Unknown fields are rejected, not silently dropped.
- **D6.** `required` is tri-state: absent stays absent (domain `None`) and is omitted from the notebook payload.
- **D7.** `job_id`: when the client supplies it, that exact value is the id sent to the notebook. When absent, keep today's generation behaviour. Both values are stored on the scene.

---

## 4. Global rules for every chunk

- Never put business logic in route functions.
- Never let `domain/` or `application/` import `infrastructure/`, `fastapi`, `kaggle` or `gradio`.
- Never hardcode account names, channel values or notebook slugs.
- Do not change the notebook or its source.
- Do not change `notebook_control.py` error handling or submission flow in this module.
- Existing legacy-format requests, existing persisted productions, and the single-video endpoints must keep working.
- Do not change the Module 1 rule: only an explicit provider-reported failure may cause `FAILED`.

---

## 5. Implementation chunks

### CHUNK 0 — Reproduce and map (READ-ONLY, no code changes)

**Objective:** find exactly where the new payload fails and map the real code against Section 2.
**Preconditions:** none.
**Instructions:**
1. Save Appendix A's payload to `/tmp/new_schema.json` (outside the repo) and POST it to the running `POST /productions`. Record the exact HTTP status and body, and the server traceback if any. Identify which layer rejects it (request schema, use case, domain, or elsewhere).
2. Do the same with a legacy-format body (`title`, `channel_id`, `scenes[]`) taken from an existing test or fixture, to confirm it still works.
3. Report the real file paths and current signatures for: the API request/response schemas for productions; `CreateProduction`/`StartProduction`; `Production`, `Scene`, `VideoGenerationRequest` (list every field and every validation rule, especially any that validate `aspect_ratio`, `resolution`, `seed`, `duration_seconds`); `ProviderCapabilities`; the generation port's batch `submit` signature (the log shows `gen_port.submit(requests)` taking a list); the generation adapter; `ComputeWorkload`; and `push_job_request`.
4. Report the **current shape of the `jobs.json` file** that is written today, and the exact place where the job ids sent to the notebook are chosen.
5. Report how a finished job's output file (`final_output/<job_id>.mp4`) is currently mapped back to its scene.
6. Report how `Production`/`Scene` are serialised in the repository, and whether old persisted records would load if new fields were added.
7. Report how API errors are currently mapped (status codes, response body shape), and which statuses a validation failure currently returns.
**Tests:** none. **Docs:** none.
**Completion criteria:** a written report with real paths, signatures and output. **STOP and wait for approval.**

---

### CHUNK 1 — Domain model

**Objective:** represent reference assets and the new job fields in the domain.
**Preconditions:** Chunk 0 approved.
**Files:** the domain package (`domain/production.py`, `value_objects.py`, `enums.py` or the real equivalents).
**Instructions:**
1. Add a `ReferenceAsset` immutable value object with the fields in 3.1, using the standard library only. `creation` is its own small value object with `method` (a new enum, `ReferenceCreationMethod`: `GENERATE`, `UPLOAD`).
2. Add `reference_assets: tuple[ReferenceAsset, ...]` to `Production` (default empty).
3. Add `reference_asset_ids: tuple[str, ...]` (default empty) to `VideoGenerationRequest`.
4. Add `client_job_id: str | None` to `Scene` (the client's key; the scene's own `scene_id` is unchanged).
5. If `VideoGenerationRequest` currently validates `aspect_ratio`, `resolution` or `seed` in a way that rejects the labels in Appendix A, relax it to "non-empty string" for the two string fields and "int" for `seed`. Record this in `KNOWN_ISSUES.md` per D3.
6. Add invariants on `Production`: asset ids unique; client job ids unique; every `reference_asset_id` on every scene exists in `Production.reference_assets`; `generate` requires `creation.prompt`; `upload` requires `uploaded_image_ref`. Violations raise the existing domain validation exception type.
**Constraints:** no third-party imports; do not change existing field meanings.
**Tests:** valid and invalid cases for every invariant above, including a production with no assets (legacy shape) staying valid.
**Documentation:** `docs/domain-model.md`; `AI_state/ARCHITECTURE_STATE.md`, `PROGRESS.md`, `KNOWN_ISSUES.md` (D3).
**Completion criteria:** domain tests green; the architecture test shows zero external imports in `domain/`. **STOP.**

---

### CHUNK 2 — Persistence compatibility

**Objective:** store the new fields without breaking existing data.
**Preconditions:** Chunk 1.
**Files:** the production repository adapter and its (de)serialisation code.
**Instructions:**
1. Serialise and deserialise `reference_assets`, `reference_asset_ids` and `client_job_id`.
2. Records saved **before** this change must still load, with the new fields defaulting to empty/`None`. No migration script. No data rewriting.
3. Reuse the existing persistence technology.
**Tests:** the shared contract test and restart-simulation test still pass; a new test loads a record saved in the old format; a round-trip test with a full new-format production.
**Documentation:** `AI_state/ARCHITECTURE_STATE.md`, `TEST_STATE.md`.
**Completion criteria:** old and new records both round-trip. **STOP.**

---

### CHUNK 3 — Ports, capability and application layer

**Objective:** carry reference assets through the use cases and the generation port.
**Preconditions:** Chunk 2.
**Files:** `application/ports.py`, `application/dto.py`, `application/use_cases.py`, the fake generation provider.
**Instructions:**
1. Add a capability value for reference-asset support to the existing `ProviderCapabilities` enum (reuse the enum; do not create a second one). Give it a neutral name, e.g. `REFERENCE_ASSETS`. Do not use the word LoRA anywhere.
2. Extend the generation port's batch `submit` with an optional `reference_assets: Sequence[ReferenceAsset] = ()` parameter. The default keeps every existing caller and fake working. Update the fake provider to record what it received.
3. `CreateProduction` accepts the new input DTO (`reference_assets`, jobs with `client_job_id` and `reference_asset_ids`, etc.), builds the domain objects, and relies on the Chunk 1 invariants.
4. `StartProduction` passes the production's reference assets to `submit`. If a production has reference assets (or any scene has `reference_asset_ids`) and the provider does not declare the capability, fail with the existing "capability unsupported" application exception **before** anything is submitted. If it has none, behave exactly as today.
5. Job id selection (D7): if a scene has `client_job_id`, that value is the job id used for the batch; otherwise keep today's behaviour. The mapping from a finished job back to its scene (Chunk 0, item 5) must keep working, using the id that was actually sent.
6. `upload` assets: raise a clear application exception "reference asset upload is not supported yet" (D4) at creation time, so a bad request fails before anything is stored.
**Constraints:** no infrastructure imports in `application/`.
**Tests (fakes only):** legacy production behaves identically; a production with assets passes them to the fake `submit`; capability missing → rejected before submit; client job ids used and mapped back correctly; upload rejected; unknown asset id rejected.
**Documentation:** `docs/ports.md`, `docs/use-cases.md`; `AI_state/ARCHITECTURE_STATE.md`, `PROGRESS.md`.
**Completion criteria:** all application tests pass with fakes only. **STOP.**

---

### CHUNK 4 — Generation adapter: emit the notebook shape

**Objective:** make the generation adapter produce exactly the Section 3.2 payload.
**Preconditions:** Chunk 3.
**Files:** the generation adapter (`infrastructure/generation/ltx25/adapter.py`), the `ComputeWorkload` definition, `push_job_request` (payload content only).
**Instructions:**
1. Extend `ComputeWorkload` (or its real equivalent) to carry reference assets alongside jobs, without Kaggle-specific details leaking into it.
2. The adapter builds the Section 3.2 structure: both keys always present; fields emitted verbatim; absent optionals omitted; no `null`s; no invented defaults. Job order is preserved.
3. `push_job_request` writes the structure it is given. Do not alter submission, polling, retry or error-handling behaviour.
4. Declare the new capability in the adapter's `get_capabilities()`.
5. Create golden fixtures in `tests/fixtures/`: Appendix A as the input request, and its expected `jobs.json` output.
**Tests:** a golden-file test (domain request in → exact JSON out, compared structurally); a legacy-production test (no assets) asserting `"reference_assets": []` and an otherwise unchanged jobs list; an omitted-optional test (no `resolution`/`seed` keys appear); the Chunk 3 contract suite still passes with the real adapter and the fake compute port.
**Documentation:** `docs/adapters/wan2gp-generation.md` (or the real adapter doc), `AI_state/ARCHITECTURE_STATE.md`, `PROGRESS.md`.
**Manual check:** none beyond the golden test. Do not trigger real Kaggle runs here.
**Completion criteria:** golden test passes. **STOP.**

---

### CHUNK 5 — API layer

**Objective:** accept the new request body at the boundary and return clean errors.
**Preconditions:** Chunk 4.
**Files:** `api/schemas.py`, `api/routers/production.py`, `api/error_handlers.py`.
**Instructions:**
1. Request schema per 3.1: `jobs` with the legacy alias `scenes`; both present is an error; optional `title` and `channel_id` with the D2 defaults; unknown fields rejected (D5).
2. Map the request schema to the application DTO in the router/schema layer. No business logic in routes.
3. Error mapping follows the project's existing convention found in Chunk 0 (validation → the status the project already uses). Messages must name the offending path, for example `jobs[2].reference_asset_ids[0]: unknown asset 'x'`. Unsupported upload → the existing "capability unsupported" status.
4. Status/result responses: include each scene's `client_job_id` when present. Do not break the existing response shape (additive only).
5. Verify that the original symptom is gone: the Appendix A payload no longer produces an unhandled error.
**Tests:** new body accepted; legacy body accepted; both `jobs` and `scenes` rejected; missing `title`/`channel_id` defaults; each validation failure (duplicate asset id, duplicate job id, unknown asset id, bad id characters, unknown field, upload method) returns the right status and a clean body with no traceback.
**Documentation:** `docs/api.md`; `AI_state/CURRENT_STATE.md`.
**Completion criteria:** all API tests pass. **STOP.**

---

### CHUNK 6 — Regression, documentation and manual verification

**Objective:** prove nothing broke and the new path works end to end.
**Preconditions:** Chunk 5.
**Instructions:**
1. Run the full test suite and the architecture tests. Report results honestly. Do not change test expectations to make failures pass.
2. Bring `docs/` and `AI_state/*` fully current (`PROGRESS.md`, `TEST_STATE.md`, `KNOWN_ISSUES.md`, `SESSION_HANDOFF.md`).
3. Manual check, to be performed by the human owner (do not claim it passed): (a) POST Appendix A, start it, and inspect the exact `jobs.json` that gets pushed; (b) confirm it matches the golden file; (c) confirm the legacy body still creates a production.
**Final report:** what changed per chunk, what is still unverified, remaining risks.
**Completion criteria:** the owner confirms the pushed `jobs.json` matches what the notebook expects.

---

## 6. Acceptance checklist

- [ ] Appendix A posts successfully and creates a production.
- [ ] A legacy `title`/`channel_id`/`scenes` body still works.
- [ ] Old persisted productions still load.
- [ ] The pushed `jobs.json` matches the golden file exactly (both keys, verbatim fields, omitted optionals, no nulls).
- [ ] Reference assets with a provider lacking the capability are rejected before any submission.
- [ ] No raw traceback reaches a client for any validation failure.
- [ ] `domain/` and `application/` still have zero infrastructure imports.
- [ ] `AI_state/SESSION_HANDOFF.md` alone is enough to resume.

## 7. Deferred (explicitly not in this module)

- Uploading user-supplied reference images to the notebook.
- Translating our neutral `aspect_ratio`/`resolution` into notebook labels (design debt D3).
- Per-asset failure handling when `required: false` assets fail to generate (notebook-side behaviour).
- Any change to chaining, assembly, or the notebook itself.

---

## Appendix A — Golden request (new schema)

```json
{
  "reference_assets": [
    {
      "asset_id": "cyber_scout_vehicle",
      "required": true,
      "creation": {
        "method": "generate",
        "prompt": "A heavily modified, matte black futuristic hover-bike with aggressively angular armor plates and glowing crimson neon repulsor engines underneath. High contrast cyberpunk aesthetic, parked on wet asphalt.",
        "aspect_ratio": "16:9"
      }
    }
  ],
  "jobs": [
    {
      "job_id": "test_scene_01",
      "prompt": "The matte black futuristic hover-bike idles inches above a rain-slicked neon street. Heavy rain violently bounces off its angular metal armor. The crimson repulsor engines pulse softly, illuminating the wet asphalt. Photorealistic, 8k. Camera control: Locked-off static wide shot to establish the reference vehicle.",
      "duration_seconds": 5,
      "chain_from_previous": false,
      "reference_asset_ids": ["cyber_scout_vehicle"],
      "aspect_ratio": "16:9 Landscape",
      "resolution": "Fast Preview (384p - ~1-2 min)",
      "seed": 42
    },
    {
      "job_id": "test_scene_02",
      "prompt": "The hover-bike suddenly accelerates forward, tearing through a deep puddle. The glowing crimson repulsors blast water outward in a massive, slow-motion wave. The matte black armor remains crisp and detailed. Camera control: Fast forward dolly, tracking alongside the bike as it launches into motion.",
      "duration_seconds": 5,
      "chain_from_previous": true,
      "reference_asset_ids": ["cyber_scout_vehicle"],
      "aspect_ratio": "16:9 Landscape"
    },
    {
      "job_id": "test_scene_03",
      "prompt": "The hover-bike sharply banks to the right, drifting around a tight corner in a dark, narrow alleyway. Sparks fly as the lower armor plating scrapes against a concrete barrier. The crimson glow trails behind it. Camera control: High-speed tracking, panning right violently to follow the sharp drift.",
      "duration_seconds": 5,
      "chain_from_previous": true,
      "reference_asset_ids": ["cyber_scout_vehicle"],
      "aspect_ratio": "16:9 Landscape"
    },
    {
      "job_id": "test_scene_04",
      "prompt": "The hover-bike launches off a steep concrete ramp, suspended in mid-air against a backdrop of towering, glowing neon skyscrapers. The matte black geometry of the bike is perfectly defined against the bright city lights. Camera control: Rapid tilt upward, catching the bike at the apex of its jump.",
      "duration_seconds": 5,
      "chain_from_previous": true,
      "reference_asset_ids": ["cyber_scout_vehicle"],
      "aspect_ratio": "16:9 Landscape"
    },
    {
      "job_id": "test_scene_05",
      "prompt": "The hover-bike slams back down onto the pavement, the crimson repulsors flaring brightly to absorb the impact. It rapidly decelerates, sliding to a smooth halt in the center of the frame. Camera control: Fast dolly back, easing to a complete stop as the bike settles into its idle hover.",
      "duration_seconds": 5,
      "chain_from_previous": true,
      "reference_asset_ids": ["cyber_scout_vehicle"],
      "aspect_ratio": "16:9 Landscape"
    }
  ]
}
```

The expected notebook `jobs.json` for this request is the same structure: `reference_assets` and `jobs` copied verbatim, in the same order, with no added or removed fields.
