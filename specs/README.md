# Specifications Documentation

This repository follows a spec-driven development approach. Specifications are organized into two categories: **canonical** (living, always up-to-date) and **working artefacts** (created to accomplish a specific task or milestone, then left as-is).

## Canonical vs Working Artefacts

### Canonical
Canonical specifications are the authoritative, current source of truth. They are kept up-to-date as the project evolves and must never go stale. They define *what* the system does and *how* it does it today.

### Working Artefacts
Working artefact specifications are created to accomplish a specific task or milestone, then left as-is. They are **not** maintained after the task is complete. Their purpose is to preserve the reasoning and context at the time of the work — useful for future LLM context windows, onboarding, or revisiting decisions. Examples include Architecture Decision Records (ADRs), slice logs, and task-tracking artifacts.

---

## Canonical Specifications

The canonical directory contains two things: the **technical charter** and the **requirements specifications** (organized in three layers).

### Technical Charter
`technical-charter.md` defines the technical governance and standards for the project — technology choices, architectural constraints, coding standards, and principles that all implementation must follow. It captures its purpose and non-negotiable constraints. If a proposed change conflicts with it, either reject the change or explicitly amend this document first.

### Requirements Specifications (Three Layers)

#### Layer 1: Requirements Specifications (`01-requirements/`)
Defines *what* the system should do. Consists of four subcategories:

- **Overall Architecture** — Defines and breaks down functionality into modules, particularly emphasizing the allowed interfaces between them.
- **Functional Requirements** — User capabilities and system behaviours in EARS format: "The [user/role] shall be able to..." with preconditions, postconditions, and notes. Must be minimal but complete.
- **Non-Functional Requirements** — Performance, security, scalability, and other quality attributes.
- **Data Requirements** — Key entities, their attributes, relationships, and domain-level invariants.
- **Third-Party Integrations** — External APIs the system depends on. Documents the API contract, required usage patterns, and constraints imposed on the implementation.

#### Layer 2: Operations/Interface/API Specifications (`02-operations/`)
Defines *how* functionality is exposed:
- Named operations on domain entities
- Preconditions, postconditions, and side-effects of each operation
- Concrete interface contracts (REST endpoints, BFF routes, GraphQL schemata, service classes, etc.)
- Request/response shapes, error codes, and authentication requirements

Multiple interface specs can technically coexist (e.g., REST and GraphQL).

#### Layer 3: User Interface Flows (`03-user-interface/`)
Defines how requirements manifest to the user:
- Concrete interaction patterns
- Screen-by-screen or step-by-step flows for each functional requirement

### Layer Relationships
All three layers reference one another and must evolve in lock-step. The typical authoring workflow:
1. Start at Layer 1 (functional requirements first)
2. Move to Layer 3 (user interface flows)
3. Use layers 1 and 3 to fill in Layer 2 (operations/API specs)

---

## Working Artefacts Specifications

### Architecture Decision Records (`@specs/working-artefacts/adr/`)
ADRs document significant architectural decisions — the problem, the chosen solution, and the rationale.

**Filename format:** `YYYY-MM-DD-scope-problem-space.md`

**Valid scopes:**
- `frontend`
- `backend`
- `data`
- `fullstack`

**Amendment rules:**
- Minor changes → amend the existing ADR in-place
- Major redesign → create a new ADR; add `Superseded by: YYYY-MM-DD-scope-problem-space.md` to the old one and `Supersedes: YYYY-MM-DD-scope-problem-space.md` to the new one

**Required sections:**
- Problem
- Design
- Implementation approach
- Decisions and open questions

**Code annotation:** When implementation code is guided by an ADR, reference it in a comment:
```
// @adr specs/working-artefacts/adr/YYYY-MM-DD-scope-problem-space.md
```

### Slice Logs (`@specs/working-artefacts/slice-logs/`)
Completed summaries of work, organized by slice. Use the template at `working-artefacts/slice-logs/TEMPLATE.md` when starting a new slice.

### Task Tracking (`@specs/working-artefacts/todos/`)
Deferred refactoring notes and R&D captured while staying focused on the current vertical slice. See `working-artefacts/todos/README.md`.

---

## File Organization

```
specs/
├── README.md                              # This file
├── canonical/                             # Living, authoritative specifications
│   ├── technical-charter.md               # Technology choices, standards, principles
│   ├── 01-requirements/                   # What the system should do
│   │   ├── functional-requirements.md
│   │   ├── non-functional-requirements.md
│   │   ├── data-requirements.md
│   │   └── third-party-integrations.md
│   ├── 02-operations/                     # How functionality is exposed
│   │   └── service-operations.md
│   └── 03-user-interface/                 # How users interact with the system
└── working-artefacts/                     # Not actively maintained
    ├── adr/                               # Architecture Decision Records
    │   └── TEMPLATE.md
    ├── slice-logs/                        # Completed work by slice
    │   └── TEMPLATE.md
    └── todos/                             # Deferred refactoring notes and R&D
        └── README.md
```

## Best Practices

1. **Keep canonical documents current** — they are the source of truth and must never go stale.
2. **Maintain traceability** between adjaced requirements layers (1<->2 and 2<->3).
3. **Use consistent terminology** across all specifications.
4. **Follow ADR conventions** for filename format, required sections, and cross-referencing.
5. **Prefer ASCII in paths and machine-readable examples**; typographic punctuation is fine in prose, but paths and code examples should be copy/paste-safe.
6. **Never mark a vertical slice as 'Complete' unless prompted to do so.**
7. **Never add features, behaviours, or UI elements that were not explicitly requested.** If a plausible enhancement seems useful, note it as an uncertainty or handoff item in the slice log and ask before implementing it. This applies to keybindings, shortcuts, menu items, dialogs, notifications, and any other observable behaviour.

## Project Lifecycle

### Phase 1: Envisioning & Scoping (Whiteboarding)
- **Goal:** Establish the project’s scope, core requirements, and technical direction.
- **Activities:** Collaborative “whiteboarding” to define the problem space, identify key entities, and outline user flows.
- **Output:** Canonical specifications only (requirements, technical charter). No working artefacts (ADRs, slice logs) are created at this stage.
- **Returnability:** For very large projects with multiple modules, the team may return to this phase later to scope subsequent modules.

### Phase 2: Implementation (Slice-Based Development)
- **Goal:** Deliver working, vertical slices of functionality.
- **Activities:** Vertical slices, commits, and the creation of working artefacts (ADRs, slice logs) as described below.
- **Trigger:** Begins when the first slice is opened for a feature that will be implemented in code.

## Development Process (Phase 2: Implementation)

*This section describes the workflow for Phase 2 (Implementation).*

### Slice-Based Development
- A vertical slice is typically a working, end-to-end piece of functionality (UI → API → data); although layer-specific slices are expected periodically
- Each slice requires 1 or more commits, althought tyically 3 or less; a commit **never** spans more than one vertical slice

### Starting a New Slice
When a new Cline task is opened for a slice:
1. Create a new slice-log file at `specs/working-artefacts/slice-logs/YYYY-MM-DD-<kebab-slice-name>.md`
2. Immediately read this README to understand the specification harness
3. Immediately read `specs/canonical/technical-charter.md`
4. Familiarize with any relevant canonical specs (requirements, operations, UI flows)

### Slice-Log Format
Slice logs follow this structure:

- **Description** – What this slice delivers and why
- **UI Flows Implemented** – Checkbox list of Layer-3 flow IDs with their required API endpoints from Layer 2
- **Dependencies** – Other slices this builds directly on
- **Referenced ADRs**
- **New ADRs created**
- **Decisions made**
- **Uncertainties** – `[ ]` / `[x]` checklist
- **Handoff notes** – What follow-on slices need to know (outstanding stubs, deferred decisions, etc.)

### Maintaining Context
- Update the slice-log as work progresses
- Close uncertainties when resolved
- Record any new ADRs created during the slice

### Closing a Slice
Before marking a slice as closed (per Best Practice 6, only when the developer prompts it), run `./scripts/check.sh` from the repo root. It runs the four gates the technical charter requires — `ruff format --check`, `ruff check`, `mypy --strict`, and `pytest` with coverage — in one command. Passing `pytest` alone is not sufficient; formatting, lint, and type-checking are separate, non-optional gates. See "Code Quality & Linting" in `technical-charter.md` for the full enforcement story, including the `githooks/pre-commit` hook that backstops this for actual commits.

