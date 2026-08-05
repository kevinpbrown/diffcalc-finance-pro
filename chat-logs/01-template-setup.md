Let's fill in @/specs/README.md  with instructions about the spec-driven nature of this repo.

You'll notice it's split in two: canonical and work-product. Canonical specs are always kept up to date with development progress, whereas work-product is used to accomplish something then kept for archival purposes. Work product are not kept up-to-date with changes, but canonical documents always remain up-to-date.

Within `canonical`, we have our requirements specifications and our technical charter. 

The requirements are divided into three layers:
1: Requirements specs
2: Operations/interface/API specs
3: User interface flows

Requirements specs can consist of:

Functional requirements: User capabilities and system behaviours. They should be minimal, but complete. "The [user/role] shall be able to..." with any relevant preconditions, postconditions and notes. They shall use the EARS format for consistency.
Non-functional requirements: Performance, security, scalability, and other attributes.
Data requirements: key entities, their attributes, relationships and domain-level invariants
3rd party integrations: APIs that the system will need to integrate with that we do not have control over. Documents the API contract, required usage, and any constraints imposed on the implementation.

Operations/interface/API specs will define:
- Named operations on domain entities
- Preconditions, postconditions, and side-effects of each operation
- Concrete interface contracts (REST endpoints, BFF routes, GraphQL schemata, etc.)
- Request/response shapes, error codes, and auth requirements

Multiple interface specs can technically coexist, although this is rare. 

User interface flows

How requirements manifest to the user. Defines:
- Concrete interaction patterns
- Screen-by-screen or step-by-step flows for each functional requirement

All of these requirements layers should reference one another. They should evolve in lock-step, but will likely be authored one layer at a time (e.g., start at Layer 1, go to Layer 3, and then let the LLM fill in the glue in Layer 2).

---

Let's go into more details on the ADRs.

The need to be stored in /specs/work-product/adr and follow a filename structure of `YYYY-MM-DD-scope-problem-space.md` where `scope` is one of:
- frontend
- backend
- data
- fullstack

ADRs can be amended over time if there are only minor changes. A major redesign should create a new ADR. We should update old ADRs with a "superseded by" reference and new ADRs should reference the old one it's superseding.

ADRs should contain sections for:
- Problem
- Design
- Implementation approach
- Decisions and open questions

When implemented code is guided by an ADR, it should add that in a comment:

`// @adr specs/work-product/adr/YYYY-MM-DD-scope-problem-space.md`

---

Now that you know about what we're specifying, let's add some information in here about our development process.

- We will create a new Cline "task" for each epic, essentially creating a new context window
- Each epic will contain somewhere between 1-5 complete vertical slices
- Each vertical slice will likely require somewhere between 1-3 commits. A commit shall never span more than a single vertical slice
- When a new chat/task is opened, a new MD file in the `epic-logs`  should be started
- The chat should immediately read this README.md to understand the specs (the "harness") and familiarize itself with any relevant specs. It should also immediately read the `technical-charter.md` document too.

The epic logs should be created at `specs/work-product/epic-logs/YYYY-MM-DD-<kebab-epic-name>.md` and documented as follows:

- Description: What this epic delivers and why
- UI Flows Implemented: checkbox list of Layer 3 flow IDs with their required API endpoints from Layer 2.
- Dependencies: Other epics this builds directly on
- Referenced ADRs
- New ADRs created
- Decisions made
- Uncertainties: `[ ]` / `[x]` checklist
- Current slice: inflight slice with a description in case the context window is interrupted
- Completed slices: `# | Title | Notes`
- Handoff notes: What follow-on epics need to know, particularly about outstanding stubs or deferred decisions

Please update any Cline configuration in this repo to do what we're requesting here. Please introduce any templates that can help accomplish this too.

---

Let's clarify in the `.clinerules` that the epic instructions and conventions apply when implementing a feature. The `epic` overhead does not apply while we're still in the envisioning stage. At the beginning of the project, we will be "whiteboarding" the scope of the project together that'll be captured in the `specs` without any code, so nothing in `work-product` (ADRs and epic logs) won't apply yet. Actually, let's capture this whole stage of development in the `specs/README.md` too -- it's a pretty critical stage. We should mention that we can return to this requirements stage later in the project if it's a very large project with multiple modules.

---

Can we also add some basic instructions in `.clinerules` so it knows what's going on in Phase 1 too? There aren't rules to enforce in Phase 1, but it'd be good to give the agent some background on the project's structure? E.g., reading `specs/README.md` is a precondition for any agent working in this repo.

---

It looks like we repeat some things between `.clinerules` and `README.md`. The repetition is strategically selected; however, please double check there isn't anything we're unnecessarily repeating in both locations. Similarly, there's repetition between the TEMPLATE.md files and what's in the README.md -- please double check that's all necessary too and prune where appropriate.