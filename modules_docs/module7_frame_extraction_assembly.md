# Module 7 — Frame Extraction & Video Assembly

Prepared by: Claude (Technical Specification Engineer)
For: Gemini CLI | Human Project Owner: Wilfred Jasper
Depends on: Module 4 (verified), Module 5 (clean artifacts), Module 6
(Production/Scene orchestration)

## 1. Module purpose
Turn an ordered set of successfully generated scene clips into one final
episode video, and enable visual continuity between scenes by chaining a
scene's final frame into the next scene's start frame.

## 2. Responsibilities
- Extract the final frame of a video artifact as a standalone image
  artifact.
- Assemble an ordered list of scene clips into one final episode artifact,
  handling the audio-variant inconsistency Module 5 introduced
  (`has_audio` may differ per scene).
- Extend Module 6's orchestration to optionally chain frames between
  scenes, and to run assembly once all scenes succeed.

## 3. Non-responsibilities
Does not decide narrative structure or which scenes should chain — that's
information the Human Project Owner supplies per scene (Module 6's
`Scene.chain_from_previous` flag). Does not implement transitions, color
grading, or any creative editing beyond ordered concatenation. Does not
implement multi-model scene routing (Section 24 of the Chief Engineer's
spec) beyond ensuring nothing here prevents it later.

## 4. Architecture — resolved investigation answers

**(G) Frame extraction boundary:** `FrameExtractionPort` in
`application/ports.py`, alongside the existing four ports. It belongs at
the application/port layer, not domain, because it performs real
infrastructure work (invoking `ffmpeg`) — exactly the same reasoning that
put `VideoGenerationPort` there in Module 4.

**(H) Assembly boundary:** `VideoAssemblyPort`, same layer, same reasoning.

Both are implemented in `infrastructure/media/ffmpeg/`, sharing one
internal `FfmpegClient` helper (wraps subprocess calls, probes streams via
`ffprobe`) used by two separate adapter classes — shared tooling, distinct
port implementations, never merged into one adapter implementing two
unrelated ports.

**Audio/normalization decision (Chief Engineer Section 16):** do not assume
raw concatenation is safe. `FfmpegVideoAssemblyAdapter` must, before
concatenating, probe every input clip's resolution, fps, codec, and audio
sample rate; if any differ (including a clip with `has_audio: false` sitting
next to ones that have audio), re-encode all clips to one common target
spec first — silence-padding the audio track for any `has_audio: false`
clip rather than dropping audio for the whole episode. This is safer than
assuming scene-to-scene consistency, especially once multi-model scenes
exist later.

## 5. Public interfaces (new)

**`FrameExtractionPort`**
- `extract_final_frame(video: ArtifactReference) -> ArtifactReference`
  (an image artifact)
- Failure: raises a domain-safe error if the video is missing/corrupt —
  never a raw ffmpeg stderr dump.

**`VideoAssemblyPort`**
- `assemble(ordered_clips: list[ArtifactReference]) -> ArtifactReference`
  (the final episode video artifact)
- Must preserve input order exactly. Must fail clearly (not silently
  produce a broken file) if any input artifact is missing.

## 6. Adapters
- `FFmpegFrameExtractionAdapter` — grabs the last decodable frame, writes
  it as a PNG/JPEG artifact.
- `FFmpegVideoAssemblyAdapter` — normalizes per Section 4, concatenates in
  order, writes the final episode artifact.
- Both depend on the shared `FfmpegClient`; both require `ffmpeg`/`ffprobe`
  to be present in the runtime environment — document this as a real
  deployment dependency, not assumed.

## 7. Data models (extensions to Module 6's `Production`/`Scene`)
- `Scene.chain_from_previous: bool` (default `False`) — when true, the
  orchestration extracts the previous scene's final frame and sets it as
  this scene's `generation_request.start_frame` before submitting.
- `Production.status` gains `ASSEMBLING` (all scenes succeeded, final
  assembly in progress) between the last scene's success and `SUCCEEDED`.
- `Production.final_artifact: ArtifactReference?` — populated once assembly
  completes.

## 8. Communication flow

**Chaining (extends Module 6's lazy-tick, per the Chief Engineer's Section
31 ordering — implement only after plain multi-scene assembly works):**
```
Scene N succeeds, artifact stored
   → if Scene[N+1].chain_from_previous:
        FrameExtractionPort.extract_final_frame(Scene[N].generated_artifact)
        → store the frame artifact
        → Scene[N+1].generation_request.start_frame = that artifact
   → submit Scene[N+1]
```

**Assembly (runs once, when the last scene succeeds):**
```
All scenes SUCCEEDED
   → Production.status = ASSEMBLING
   → VideoAssemblyPort.assemble([scene.generated_artifact for scene in order])
   → ArtifactStoragePort.store() the result under
     productions/<id>/final/episode.mp4
   → Production.final_artifact = that reference
   → Production.status = SUCCEEDED
```

`GET /productions/{id}/artifact` (from Module 6) now has two real
behaviors depending on state: while `RUNNING`/`ASSEMBLING`, it returns
per-scene artifacts available so far; once `SUCCEEDED`, it returns
`Production.final_artifact` — document this state-dependent response
explicitly in the API docs so it isn't mistaken for two different
endpoints.

## 9. Persistence
`Scene.chain_from_previous`, `Production.status` (`ASSEMBLING` value), and
`Production.final_artifact` are new fields on already-persisted aggregates
— no new repository, just an extended schema for the existing
`ProductionRepositoryPort` implementation from Module 6.

## 10. Artifact lifecycle
Extends Module 6's flow: scene clips (already covered) plus, new here,
extracted frame images (`productions/<id>/scenes/<id>/final_frame.png`)
and the final episode (`productions/<id>/final/episode.mp4`).

## 11. Testing
- **`FrameExtractionPort`**: successful extraction, missing video, corrupt/
  invalid video — using fakes for orchestration tests, and a real-`ffmpeg`
  integration test for the adapter itself (not a unit test — this one
  genuinely needs the real binary).
- **`VideoAssemblyPort`**: ordered clips assemble correctly; mismatched
  resolution/fps/audio triggers normalization (assert the adapter actually
  re-encodes rather than failing or silently dropping audio); missing input
  fails clearly.
- **Orchestration**: using fakes for both new ports, prove chaining wires
  the correct frame into the correct next scene's request; prove assembly
  only triggers once *all* scenes succeed, never partially.

## 12. Manual testing — last-frame chaining (Chief Engineer Section 31)
Only after Section 12's plain multi-scene test (Module 6) already passes:
1. Create a production where scene 2 and 3 have `chain_from_previous: true`.
2. Start it; let all scenes complete.
3. Manually inspect each extracted frame image — does it visually match the
   end of its source clip?
4. Confirm scene 2 and 3's generated video visually begins near where the
   prior scene's frame looked.
5. Confirm the final assembled episode plays scenes 1→2→3→4→5 in order,
   with audio throughout (including a silence-padded segment for any scene
   that lost its audio track per Module 5's fallback).

## 13. Extension guide
A future multi-model workflow (Section 24 of the Chief Engineer's spec)
generates Scene N via a different `VideoGenerationPort` adapter — chaining
and assembly are unaffected, since both operate purely on
`ArtifactReference`s, never on provider-specific representations.

## 14. Gemini implementation chunks

### CHUNK 7.0 — Prerequisite Gate
**Objective:** Confirm Module 6's plain multi-scene pipeline (no chaining) actually works end-to-end before starting this module.
**Manual check:** Human Project Owner confirms Module 6's Section 12 manual test already passed for real.

### CHUNK 7.1 — FrameExtractionPort + FFmpeg Adapter
**Files/modules affected:** `application/ports.py` (add the port), `infrastructure/media/ffmpeg/frame_extraction.py`, `infrastructure/media/ffmpeg/client.py`.
**Tests:** Fakes-based contract test; one real-ffmpeg integration test (marked manual/opt-in, same convention as the real-Kaggle test).
**Manual check:** Extract a frame from a real generated clip; open the image; confirm it looks like the end of the video.
**Documentation:** `docs/ports.md`, `docs/adapters/ffmpeg-frame-extraction.md`; `AI_state/ARCHITECTURE_STATE.md`.

### CHUNK 7.2 — VideoAssemblyPort + FFmpeg Adapter (no chaining yet)
**Files/modules affected:** `application/ports.py`, `infrastructure/media/ffmpeg/assembly.py`.
**Implementation instructions:** Implement the normalization-before-concat logic from Section 4 explicitly — do not assume clips are compatible.
**Tests:** Ordered assembly, mismatched-input normalization (assert re-encoding actually happens), missing-input failure — per Section 11.
**Manual check:** Assemble two real, deliberately-different-resolution test clips; confirm the output plays correctly with no visual glitch at the join.
**Documentation:** `docs/adapters/ffmpeg-assembly.md`.

### CHUNK 7.3 — Wire Assembly into Production Orchestration
**Objective:** Extend Module 6's lazy-tick so `ASSEMBLING`/`final_artifact` happen automatically once all scenes succeed.
**Files/modules affected:** Module 6's orchestration use case; `Production` domain model (add `ASSEMBLING`, `final_artifact`).
**Tests:** All-scenes-succeed triggers assembly exactly once; a scene failure never triggers assembly.
**Manual check:** Run the full Module 6 five-scene manual test again; confirm it now ends with a real assembled episode file, playable, correct order.
**Documentation:** Update `docs/use-cases.md`, `AI_state/PROGRESS.md`.
**Completion criteria:** Section 12 of Module 6 now additionally produces a real final episode artifact.

### CHUNK 7.4 — Last-Frame Chaining
**Objective:** Implement `Scene.chain_from_previous` and the extraction-then-feed-forward logic from Section 8.
**Constraints:** Do not build this before Chunk 7.3 is confirmed working, per the Chief Engineer's explicit sequencing.
**Tests:** Per Section 11's chaining test.
**Manual check:** Section 12's full chaining manual test, run for real.
**Documentation:** `docs/use-cases.md` updated; `AI_state/PROGRESS.md`, `KNOWN_ISSUES.md` if anything about frame-to-start-frame translation proves imperfect.
**Completion criteria:** A real chained production visually confirms continuity between scenes.

### CHUNK 7.5 — API & Documentation Finalization
**Objective:** Document the state-dependent behavior of `GET /productions/{id}/artifact` (Section 8) and finalize all Module 7 docs/`AI_state`.
**Completion criteria:** The full chain from the Chief Engineer's original Definition of Done (Section 36) is demonstrably true, end to end, for real.
