# Module 5 — Artifact Retrieval Cleanup

Prepared by: Claude (Technical Specification Engineer)
For: Gemini CLI | Human Project Owner: Wilfred Jasper
Depends on: Module 1 (verified complete via Chunk 5.0 below, not assumed)

## 1. Module purpose
A generation currently produces up to six redundant copies of the same
video locally (two audio variants × three separate write locations). Fix
this at both ends: the notebook must produce and keep exactly one canonical
file, and the adapter must defensively retrieve only that file regardless
of what else exists.

## 2. Responsibilities
- The Kaggle notebook writes exactly one canonical output file per job and
  deletes everything else (source files, job request, logs, the full
  Wan2GP working tree) before exiting.
- `KaggleComputeAdapter.get_result()` identifies and returns only that
  canonical file's `ArtifactReference`, never a raw directory dump.

## 3. Non-responsibilities
Does not introduce Production/Scene/Episode concepts (Module 6). Does not
touch assembly or frame extraction (Module 7). Does not change
`VideoGenerationPort`'s public shape — only what correctly populates
`GenerationResult.output_artifacts`.

## 4. Architecture
Entirely inside the Kaggle compute boundary established in Module 4:
`infrastructure/compute/kaggle/notebook_source/*` and
`infrastructure/compute/kaggle/adapter.py`. No other layer changes.

## 5. Public interfaces
No new ports. Contract clarification only:
`ComputeExecutionPort.get_result()` must return exactly the artifact(s) a
caller actually asked for — never incidental files the provider happened
to also produce.

## 6. Adapters
`KaggleComputeAdapter.get_result()` gains explicit canonical-filename
matching. Anything else present in the downloaded tree is logged and
discarded by default; a separate, explicit `debug=True` parameter can
retrieve the full raw tree for troubleshooting — production code paths
never set it.

## 7. Data models
No new types. `ArtifactReference` (from Module 4) is reused as-is.

## 8. Communication flow — root cause and fix
**Confirmed root cause (three stacking sources, not one):**
1. Wan2GP's own `Video_Generation` function copies its output to
   `Wan2GP/outputs/`.
2. The same function additionally copies to a top-level
   `/kaggle/working/outputs/` "for external access" — pure duplication,
   serving no purpose now.
3. My earlier headless-Step-4 fix copies again to `/kaggle/working/final_output/`.

Each of those three locations holds both the plain and `_with_audio`
variant — six files for one generation.

**Fixed flow:**
```
Generation completes inside Wan2GP
   → write the with-audio result DIRECTLY to
     /kaggle/working/final_output/<job_id>.mp4 — one write, one location
   → the redundant Wan2GP/outputs and top-level outputs/ copies are removed
     from the generation code path entirely (not copied there at all)
Headless Step 4, before exiting:
   → deletes job_request/, run_aiquest_ltx25.py, run_aiquest_ltx25_headless.py,
     any *.log files, and the entire Wan2GP/ tree
   → /kaggle/working now contains only final_output/<job_id>.mp4
Kernel completes → kaggle kernels output → adapter finds exactly one file
   matching final_output/*.mp4 → returns its ArtifactReference
```

**Canonical artifact decision (answers Chief Engineer's Section 27-D):**
the `_with_audio.mp4` variant is canonical. Inspection of the generation
code shows `out_path` is reassigned to the audio-muxed file on success —
the plain file is an intermediate step toward that result, not a deliverable
in its own right. If audio muxing fails, the plain file becomes canonical
by fallback, and this must be recorded in the result metadata (`has_audio:
false`) rather than silently treated as equivalent — Module 6/7's assembly
step needs to know this per scene.

## 9. Persistence
Not applicable to this module.

## 10. Artifact lifecycle
Kaggle notebook → one canonical file → `KaggleComputeAdapter` →
`ArtifactReference` (local temp path) → handed to whatever called
`VideoGenerationPort` (today: the single-video use case; Module 6 will be
the next caller).

## 11. Testing
- **Notebook cleanup logic**: refactor the "what to keep, what to delete"
  decision into a plain Python function testable without a real kernel;
  test it directly.
- **Adapter test (the critical regression test from the Chief Engineer's
  Section 29)**: construct a mock downloaded directory tree that
  *exactly* reproduces the redundant structure observed in production
  (nested UUID subfolder, duplicate `outputs/`/`final_output/`, both audio
  variants) and assert `get_result()` returns exactly one
  `ArtifactReference`, pointing at the with-audio file, ignoring
  everything else.
- **Audio-fallback test**: mock a completed job with only the plain
  variant present; assert it becomes canonical with `has_audio: false`
  recorded.

## 12. Manual testing
1. Trigger one real generation end-to-end.
2. Download the result and confirm it's a **single file**, not a nested
   workspace.
3. Confirm it's the with-audio variant and plays correctly with sound.
4. Re-check the Kaggle notebook's own `/kaggle/working` listing (via the
   web UI) after the run — should show only `final_output/` with one file
   in it, nothing else.

## 13. Extension guide
Any future provider adapter (Veo, a hosted API) follows the same two-layer
discipline: the provider-side integration produces one clean artifact where
possible, and the adapter defensively filters for exactly what was asked
for regardless. Never trust a provider's raw output listing as-is.

## 14. Gemini implementation chunks

### CHUNK 5.0 — Prerequisite Gate
**Objective:** Confirm Module 4 is actually complete before touching anything here.
**Implementation instructions:** Read `AI_state/CURRENT_STATE.md`. Confirm all of: FastAPI is live, `Wan2GPVideoGenerationAdapter` and `KaggleComputeAdapter` are fully implemented (all six Chunk 4 behaviors), a real generation has been verified through the API (Module 4 Chunk 11). If any of this is not true, STOP and report exactly what's missing — do not proceed into Module 5.
**Manual check:** Human Project Owner confirms Gemini's report matches reality before continuing.
**Completion criteria:** Explicit "Module 4 confirmed complete" or a clear stop-and-report.

### CHUNK 5.1 — Inspect & Confirm Redundancy Source
**Objective:** Verify the three-source duplication theory in Section 8 against the actual current notebook code, before changing anything.
**Files/modules affected:** Read-only inspection of `infrastructure/compute/kaggle/notebook_source/*`.
**Implementation instructions:** Locate the exact lines producing each of the three copies described in Section 8. Report back the exact file/line locations. If reality differs from this spec's description, report the conflict rather than proceeding on a wrong assumption.
**Tests:** None (inspection only).
**Manual check:** Human Project Owner reviews Gemini's findings before Chunk 5.2 begins.
**Completion criteria:** All three duplication sources located and confirmed, or discrepancy reported.

### CHUNK 5.2 — Notebook Cleanup Redesign
**Objective:** Implement the fixed flow from Section 8.
**Files/modules affected:** The generation code inside `run_aiquest_ltx25*.py`'s template (wherever it's now sourced per Module 4's Chunk 0 assembly) and the headless Step 4 cell.
**Implementation instructions:** Remove the two redundant copy operations entirely (Section 8, sources 1–2). Write the canonical output directly to `final_output/<job_id>.mp4` in one step. Confirm the existing end-of-run cleanup (deleting `Wan2GP/`, job request, logs) still runs after this change.
**Constraints:** Do not change the underlying generation call/parameters — only where the result gets written and what gets cleaned up.
**Tests:** The refactored cleanup-decision function's unit tests from Section 11.
**Manual check:** Trigger one generation; confirm via the Kaggle web UI that `/kaggle/working` contains only `final_output/` at the end of the run.
**Documentation:** Update `AI_state/PROGRESS.md` and `KNOWN_ISSUES.md` (mark the redundancy issue fixed, with date/chunk reference).
**Completion criteria:** A real run produces exactly one file in `/kaggle/working` at completion.

### CHUNK 5.3 — Adapter Canonical-Artifact Filtering
**Objective:** Make `KaggleComputeAdapter.get_result()` defensively filter for the canonical file regardless of what the notebook produced.
**Files/modules affected:** `infrastructure/compute/kaggle/adapter.py`.
**Implementation instructions:** Implement the matching/filtering logic from Section 6, including the `has_audio: false` fallback path from Section 8's canonical-artifact decision. Add the `debug=True` escape hatch.
**Tests:** The critical regression test and audio-fallback test from Section 11 — both must pass using the exact redundant mock structure observed in production, not a simplified stand-in.
**Manual check:** None needed beyond the automated test — this behavior is fully mockable.
**Documentation:** Update `docs/adapters/kaggle-compute.md` and `AI_state/ARCHITECTURE_STATE.md`.
**Completion criteria:** Both tests pass; adapter never returns more than the requested artifact(s) even against a deliberately messy mock tree.

### CHUNK 5.4 — End-to-End Regression Verification
**Objective:** Prove Chunks 5.2 and 5.3 together produce the desired real-world result.
**Implementation instructions:** Run one real generation through the full stack (API → use case → port → adapter → Kaggle → back).
**Manual check:** Confirm locally you receive exactly one playable, with-audio video file — not a directory, not duplicates.
**Documentation:** Record the real result in `AI_state/PROGRESS.md` and `TEST_STATE.md` — do not claim success unless actually observed.
**Completion criteria:** One real generation, one real local file, confirmed by the Human Project Owner.

### CHUNK 5.5 — Documentation Finalization
**Objective:** Bring `docs/adapters/kaggle-compute.md` fully up to date with the final behavior.
**Completion criteria:** A fresh reader understands the canonical-artifact contract without reading this spec.
