# Implementation — Documentation (game project)

> **Studio function:** Technology

How to **record** a change in the Godot game project. Pair with `/tech_implementation` (how to build)
and `/tech_implementation_testing` (how to validate). Documentation is part of "done" — a change is
incomplete until all three surfaces below are updated and in sync.

**This skill is game-agnostic.** The project root, the ticket-ID prefix, and the doc folder names
are conventions the **game project defines in its own `CLAUDE.md`** — read them there. The structure
below (three surfaces, six ticket sections) is the reusable part. All docs are plain text/markdown.

Three surfaces, three jobs:
- `changelogs/` — **change history** (what changed, why, how tested, result).
- `logic/` — **current implementation** (how a system works right now).
- `docs/IMPLEMENTATION.md` (or the project's progress tracker) — the step plan + asset wiring.

Keep the game project's `CLAUDE.md` **lean** — durable orientation + pointers only; detail lives in
the three surfaces above, never in CLAUDE.md.

---

## 1. Changelog ticket — `changelogs/<TICKET-ID>-<slug>.md`

Use the project's ticket-ID prefix (defined in its CLAUDE.md). One file per delivered unit of work.
Add the row to `changelogs/README.md`. Mandatory sections, in order:

1. **Header table** — Type / Priority / Status / Date / Engine / Depends-on.
2. **Description** + **Acceptance criteria**.
3. **Previous state (before this change)** — the prior code/scene/config, with snippets.
4. **Implementation details** — per-file breakdown of *what changed and the logic* (behavior /
   algorithm + key config values, not just file names). Include the resolved gotchas (e.g. a
   resource-format fix, an init-order fix) and any required ripple edits (e.g. updated path refs).
5. **Testing** — the **actual commands and test scripts used, reproduced verbatim**: the engine
   invocations, any throwaway test/generator scripts in full, and the temp instrumentation snippets.
   (Get these from `/tech_implementation_testing`.)
6. **Results** — the **real output**, quoted (e.g. an invariant line like `STATE OK: nodes=… edges=…`,
   or a behavior line like `value 0->1 signal=true`). If a test surfaced a bug that was then fixed,
   show both. Follow with **Follow-ups / notes** (incl. HITL tuning values left for the human).

## 2. Logic doc — `logic/<system>.md`

The living "current implementation" reference. Rules:
- Describes how the system works **right now** — NOT change history. No before/after, no testing.
- Carries **code-level detail of the current state**: key code snippets, exact config/constant
  values (scales, radii, intervals, frame counts, fps, limits), per-file logic — same depth as a
  ticket's Implementation-details section, current-state only.
- Update the affected file(s) whenever behavior changes; for a new system add a file and link it
  in `logic/README.md` (and update the system map there).

## 3. Progress tracker — `docs/IMPLEMENTATION.md`

- Tick the step checkbox with a one/two-line summary + the verification headline.
- Update the asset-wiring tables (mark wired assets **Done (Step N)**; strike replaced/orphaned
  placeholders).

## 4. CLAUDE.md (lean)

Only update the game project's `CLAUDE.md` if durable orientation changed (scene tree shape, core
modules, conventions pointer). Never paste step progress, asset tables, or test output here.

---

## Definition of done (documentation)

A `changelogs/<TICKET-ID>` ticket exists with all six sections (including verbatim test scripts and
real results), the relevant `logic/` doc reflects the new current state, the progress tracker is
ticked/updated, and `CLAUDE.md` stayed lean. Cross-link related docs.
