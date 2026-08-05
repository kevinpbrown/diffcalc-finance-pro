# Personal Finance App Rules

This project uses harness engineering and spec-driven development to support an entirely LLM-driven development process.

## General Rules

CRITICAL: When you encounter a file reference (e.g., @rules/general.md), use your Read tool to load it on a need-to-know basis. They're relevant to the SPECIFIC task at hand.

- Do NOT preemptively load all references - use lazy loading based on actual need.
- When loaded, treat content as mandatory instructions that override defaults.
- Follow references recursively when needed.
- Never under any circumstances should you automatically commit anything to VCS. If a commit is recommended, please generate its commit message and ask the developer to complete the process.
- Do not scan the entire repo unless asked. If you get lost, please ask the prompter for more details.

## Development Environment

The project uses a local virtualenv managed by Hatch. Neither `python`, `hatch`, nor `uv` are on the system PATH — invoke tooling directly through the virtualenv:

- **Run tests:** `.venv/bin/pytest`
- **Run the app:** `.venv/bin/personal-finance`
- **Run scripts:** `.venv/bin/python scripts/<name>.py`
- **Run full charter compliance check** (format, lint, `mypy --strict`, tests+coverage): `./scripts/check.sh`
- **One-time setup, once per clone:** `git config core.hooksPath githooks` — installs a pre-commit hook that runs `scripts/check.sh` and blocks the commit on failure. Without this, formatting/lint/type drift accumulates silently (see [2026-08-06 slice log](specs/working-artefacts/slice-logs/2026-08-06-pre-publish-charter-audit.md) for the incident that prompted this).

**Non-negotiable (per technical-charter.md):** Run `./scripts/check.sh` before telling the user a slice is ready to close, and before generating any commit message. Do not rely on `pytest` alone — formatting, lint, and `mypy --strict` are separate gates that pytest does not cover.

## Project Development Lifecycle

**General Context for All Work**
- **Precondition:** Before any work in this repository, always read @specs/README.md to understand the specification harness and the two-phase lifecycle. Only if doing development work, read @specs/canonical/technical-charter.md for the technical invariants for this project.
- **Layer READMEs:** Each source subdirectory (`src/personal_finance/ui/`, `src/personal_finance/service/`, etc.) has a `README.md` containing layer-specific constraints, conventions, and known gotchas. Read the README for any layer you are about to write or modify code in. These are canonical documents — keep them up to date when new gotchas or conventions are discovered and remove old ones that no longer apply.
- **Phase 1 (Envisioning/Scoping):** Focus on creating and refining canonical specifications (requirements, technical charter). No working artefacts (ADRs, slice logs) are created at this stage.
- **Phase 2 (Implementation):** Follow the slice-based development process described below.

You can generally assume that if the prompt is starting with requirements whiteboarding, we're in Phase 1. If the prompt assumes implementation, then we're in Phase 2. Please clarify if there is any ambiguity on what phase we're currently in. 

### Phase 2 Instructions

**Applicability:** The detailed rules below apply during the **implementation phase** (Phase 2) when building features. During Phase 1, only canonical specifications are created; working artefacts are not needed.

When a new context window is opened for a slice, follow these steps:

#### Immediate Actions
1. **Create a slice log:**
   - Generate a new slice-log file at `@specs/working-artefacts/slice-logs/YYYY-MM-DD-<kebab-slice-name>.md` if it doesn't already exist. The prompter should start off their context window referencing the current slice or describing a new one.
   - Use the template at `@specs/working-artefacts/slice-logs/TEMPLATE.md` as a starting point

2. **Read the harness:**
   - Read @specs/README.md to understand the specification harness
   - Read @specs/canonical/technical-charter.md for technical constraints

3. **Familiarize with relevant specs:**
   - Review any canonical specs (requirements, operations, UI flows) that relate to this slice

#### Development Process
- Follow the slice-based development process described in @specs/README.md
- A vertical slice is a working, end-to-end piece of functionality (UI → API → data)
- Each slice requires 1-3 commits; a commit never spans more than one vertical slice
- Update the slice-log as you progress

#### Working Artefact Conventions
- **ADRs:** Follow the conventions in @specs/README.md (filename, scopes, amendment rules, required sections)
- **Code annotation:** `// @adr specs/working-artefacts/adr/YYYY-MM-DD-scope-problem-space.md`
- **Slice logs:** Working artefact; not maintained after slice completion

#### Traceability & Context
- Link UI flows (Layer-3) to required API endpoints (Layer-2)
- Keep the "UI Flows Implemented" checkbox list up to date
- Record any new ADRs created during the slice
- Close uncertainties when resolved
- Provide clear handoff notes for follow-on slices
