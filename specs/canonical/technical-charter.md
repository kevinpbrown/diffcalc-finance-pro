# Technical Charter

This document defines the technical governance and standards for the Personal Finance Textual UI project — technology choices, architectural constraints, coding standards, and principles that all implementation must follow. It captures its purpose and non‑negotiable constraints. If a proposed change conflicts with it, either reject the change or explicitly amend this document first.

## Purpose

The Personal Finance Textual UI is a desktop application that replaces a manual Excel‑based personal finance tracking system. It provides three core modules (balance sheet, goals, cash flow) in a terminal‑based interface, enabling users to monitor net worth, allocate assets to goals, and project monthly cash flow.

This charter ensures that all technical decisions align with the project’s goals: correctness, security, usability, and maintainability.

## Technology Stack

### Core Language
- **Python 3.12+** – the primary implementation language.
- **Rationale:** Rich ecosystem, excellent support for financial calculations (Decimal), strong typing via type hints, and mature libraries for UI (Textual) and data persistence.
- **Non‑negotiable:** All new code must be written in Python 3.12 syntax or later, with full type hints.

### User Interface Framework
- **Textual** – a modern, reactive terminal UI framework for Python.
- **Rationale:** Provides a rich, interactive experience in the terminal with keyboard‑first navigation, theming, and widget library. It aligns with the goal of a lightweight, non‑web desktop application.
- **Non‑negotiable:** The UI shall be built exclusively with Textual; no other GUI toolkit (Tkinter, PyQt, web‑based) shall be used.

### Data Persistence
- **SQLite** and **SQLAlchemy**
- **Rationale:** SQLite is a serverless, file-based database that supports ACID transactions. SQLAlchemy provides an enterprise-pattern ORM. The implementation must follow a "Domain Model-First" approach, where the SQL schema is generated directly from the SQLAlchemy models.
- **Non-negotiable:** All persistent application data (except configuration and logs) must reside in the SQLite database. During development, the database will be dropped and recreated from scratch on schema changes—schema migration tools (like Alembic) are not required until production. Configuration and mock data seeding shall be automated via a documented Python script.

### Configuration Storage
- **TOML** (via `tomli`/`tomllib`) for human‑editable configuration files.
- **Rationale:** TOML is readable, supports hierarchical structures, and has good Python library support. Configuration files shall be placed in a standard OS‑specific application directory (e.g., `~/.config/personal‑finance‑sdd/`).
- **Non‑negotiable:** System‑wide enumerations (owner identifiers, investment types, etc.) must be defined in TOML configuration, not in source code.

### Testing Framework
- **`pytest`** for unit and integration tests.
- **`pytest‑asyncio`** for async tests.
- **`pytest‑cov`** for coverage reporting.
- **Rationale:** `pytest` is the de‑facto standard for Python testing, with extensive plugin support and clear syntax.
- **Non‑negotiable:** All domain models and services require at least 80% line coverage of core business logic. This coverage must be confirmed before a vertical slice can be closed. User interface logic does not require this strict threshold, but a reasonable baseline of testing should still be established.

### Code Quality & Linting
- **Non-negotiable:** Every vertical slice must be fully linted and pass type-checking (e.g., via `mypy` and `flake8`/`ruff`) before the slice can be marked closed.
- **Enforcement mechanism:** `./scripts/check.sh` runs `ruff format --check`, `ruff check`, `mypy --strict`, and `pytest` (with coverage) in one command — this is the authoritative check, not any individual tool run in isolation. A tracked pre-commit hook at `githooks/pre-commit` blocks commits that fail it; enable it once per clone with `git config core.hooksPath githooks` (see `AGENTS.md`). An LLM session must run `./scripts/check.sh` before reporting a slice as ready to close.

### Logging
- **`structlog`** or standard `logging` module with structured output.
- **Rationale:** Structured logs improve debuggability and can be easily ingested by log aggregation tools.
- **Non‑negotiable:** Logs must include timestamps, severity, module name, and relevant context (e.g., account ID). Sensitive data (balances, personal identifiers) must not appear in logs.

## Architectural Constraints

### Architectural Layers
The application shall be structured using a strict three-layer architecture:
1. **Domain Layer**: Contains business logic, SQLAlchemy models, validation rules, and decimal math. Use **Rich Domain Models** whenever logic is specific to the rules of the domain.
2. **Service/Operations Layer**: Contains transaction scripts divided into two sub-layers:
   - **`service/core/`** — reusable domain operations that map to named operations in the service-operations spec. These must have no knowledge of how any screen presents their output and must be independently testable without Textual.
   - **`service/application/`** — screen-level aggregation (BFF pattern). These orchestrate one or more core services to fulfil a specific screen's data contract. Thin proxies are acceptable and expected.

   If there is ambiguity about which sub-layer a piece of logic belongs in, explicitly ask the user for guidance.
3. **User Interface Layer**: The Textual TUI code.

**Non-negotiable:** The UI must never bypass the service layer to talk directly to the domain or database. The domain must never depend on the service or UI layers.

**Non-negotiable:** Each UI screen must interact exclusively through its own dedicated application service — screens must not call application services that belong to other screens. Application services may orchestrate calls to any core service, including core services from other submodules (e.g. a Goals application service calling `BalanceSheetService`). Core services may call other core services but must never import from `service/application/` or the `ui/` layer. Core service methods must reside in the service file for their own module — a method stays in `balance_sheet_service.py` even when it is called by `goal_service.py`.

### Derived Fields
Derived fields should not be persisted in the schema unless there is a proven performance reason to do so.
**Non-negotiable:** If an LLM believes persisting a derived field is necessary for performance, it must recommend the change to the user and receive explicit permission before proceeding.

### Directory Structure and Organization
The project directory structure must clearly reflect the application's architectural layers as the primary organizational boundary, with feature submodules acting as secondary divisions.

- **`src/personal_finance/`**: The primary source code module.
  - **`domain/`**: Domain layer code (models, business logic, schemas).
  - **`service/`**: Service/Operations layer code.
    - **`service/core/`**: Reusable domain operations (one file per module, e.g. `balance_sheet_service.py`). Cross-cutting operations live in `general_service.py`.
    - **`service/application/`**: Screen-level aggregation services (one file per screen group, e.g. `dashboard_service.py`).
  - **`ui/`**: User Interface layer (Textual application and widgets).
- **`tests/`**: All automated test suites, structured to mirror the `src` directory.

Within the `domain` layer, the code is further divided into application submodules (e.g., `balance_sheet`, `goals`, `cash_flow`). Code shared between submodules remains in the `domain` root. The `service/core/` and `service/application/` layers use flat file naming rather than subdirectory nesting — see **File Naming** in the Coding Standards section.

**Non-negotiable:** The domain, service, and TUI layers must come first when organizing the project. The application submodules (Balance Sheet, Cash Flow, Goals) are secondary divisions meant for encouraging clean interfaces rather than isolated silos. Dependencies between these submodules must be strictly unidirectional:
- `goals` may depend on `balance_sheet` (to reference accounts/holdings).
- `cash_flow` may depend on `balance_sheet` and `goals`.
- No circular dependencies are allowed.

**Non-negotiable:** UI screens must only import from `service/application/`. Direct imports from `service/core/` in the UI layer are prohibited. Core services must not import from `service/application/` or the `ui/` layer.

**Non-negotiable:** Within the service layer, entity retrieval must go through the appropriate core service method, not directly through the SQLAlchemy session. Core service methods may perform post-load enrichment (e.g. injecting market prices into listed security holdings) that a raw session query silently bypasses. A direct `session.query(...)` call in a service that has a corresponding core service method is a bug, not an optimisation.

### Dependency Injection
All third‑party integrations (price providers, forex providers, email, etc.) shall be accessed through abstract base classes (ABCs) defined in `core.interfaces`.

**Non‑negotiable:** Concrete implementations must be injectable via configuration. The application shall not instantiate concrete providers directly; instead, use a factory or dependency‑injection container.

### Configuration‑Over‑Code
Household-specific values that genuinely vary between users must be defined in TOML configuration, not hard-coded. This currently covers:

- **Owner identifiers** (`Person` names) — adding a new owner (e.g., "Child") must not require a code change.
- **Asset class names** (`AccountAssetClass`) — the master list of categorizations a household tracks.
- **Numeric tunables** (e.g., `amount_left_to_invest_cushion`, `same_day_quote_ttl_seconds`).

Domain enumerations whose value sets are determined by the financial domain itself — `AccountClassification`, `SimpleAccountCategory`, `InvestmentRegistration` (CRA-defined), `EffectiveAmountEntrySource`, and the `HouseholdExpense*` enums — are intentionally hard-coded as Python `enum.Enum` types. Adding a new value to these is a design decision that warrants a code change, not a configuration edit.

**Non‑negotiable:** The code shall read configuration at startup and validate it. The categories listed above must not require a code change to extend.

### Data Validation
All user‑provided data must be validated using **Pydantic** models or similar schema‑based validation.

**Non‑negotiable:** No raw dictionaries or unvalidated tuples shall be passed between modules. Validation errors must produce user‑friendly messages.

### Decimal Arithmetic
All monetary values and percentages shall use Python’s `decimal.Decimal` with explicit context settings to avoid floating‑point rounding errors.

**Non‑negotiable:** `float` shall not be used for money, percentages, or any financial calculation. The decimal context shall be set to `decimal.getcontext().prec = 28` and `decimal.getcontext().rounding = decimal.ROUND_HALF_UP`.

### Soft-Delete Pattern
Any domain entity that supports soft-deletion must:
- Inherit the `Discardable` mixin from `personal_finance.domain.base`.
- The mixin provides the `date_discarded` mapped column, an `is_discarded` property (boolean), and a `discard()` method.

**Non-negotiable:** No service, application, or UI code may assign `date_discarded` directly. All soft-deletes must call `entity.discard()`, which raises `ValueError` if the entity is already discarded.

### Immutable Data for Core Entities
Core domain entities (Account, Goal, Holding, etc.) shall be immutable once persisted. Changes shall produce a new version with an updated `updated_at` timestamp.

**Non-negotiable:** Update operations shall be implemented as "replace-with-new" rather than in-place mutation. This architecture is selected to leave the system open for adding auditability features in the future.

## Coding Standards

### Type Hints
All function and method signatures must include type hints. Return types must be specified; `None` returns must be explicit.

**Non‑negotiable:** The codebase shall pass `mypy --strict` (or equivalent) with no errors.

### Code Formatting
- **Ruff** (or **Black** + **isort**) must be used as a strictly opinionated automatic code formatter.
- **Rationale:** Complete consistency is prioritized over any given standard. Much like Prettier in Node, an opinionated formatter eliminates style debates and cognitive overhead.
- **Non‑negotiable:** All commits must be formatted automatically. The development environment must be configured to format on save. Complete code consistency across the entire codebase is strictly enforced.
- **Enforcement mechanism:** the `githooks/pre-commit` hook (see Code Quality & Linting above) runs `ruff format --check` and blocks any commit that would introduce drift. Format-on-save is a per-editor setting this repo cannot enforce directly; the pre-commit hook is the backstop that catches it regardless of editor configuration.

### File Naming
Every source file must be named after its primary content. Generic filenames (`service.py`, `utils.py`, `helpers.py`, `models.py`) are not permitted. A file may contain multiple related classes or functions when all share a clear single subject (e.g. `holding.py` for holding-related data classes). When subject boundaries blur, split into additional well-named files rather than reaching for a catch-all name.

**Non-negotiable:** Any file whose name does not immediately convey its contents must be renamed as part of the slice that introduces or modifies it.

### Documentation
- **Google‑style docstrings** for all public modules, classes, and functions.
- **README.md** in each package explaining its purpose and key concepts.
- **Rationale:** Good documentation is essential for long‑term maintainability and onboarding.
- **Non‑negotiable:** Any function with non‑trivial logic must have a docstring describing its behaviour, parameters, return value, and possible exceptions.

### Error Handling
- Use typed exceptions (subclasses of `ValueError`, `RuntimeError`, or custom domain exceptions).
- Never catch generic `Exception` unless re‑raising with additional context.
- **Non‑negotiable:** Errors that are expected (e.g., validation failures) must not raise generic exceptions; they should return a `Result`‑type or raise a specific, documented exception.

### Concurrency
- Use `asyncio` for I/O‑bound operations (network calls, file I/O).
- Use `threading` or `multiprocessing` only for CPU‑bound tasks that would block the UI.
- **Non‑negotiable:** The UI thread (Textual’s event loop) must never be blocked for more than 100 ms. Long‑running operations shall be off‑loaded to background tasks with progress indication.

## Security Constraints

### Network Security
All external HTTP/HTTPS requests must:
- Validate TLS certificates.
- Use timeouts (default 10 seconds).
- Never include sensitive data in URL query parameters.
- **Non‑negotiable:** Disable SSL verification is forbidden.

## Deployment & Distribution

### Installation Directory
User data (database, configuration, logs) shall be stored in platform‑specific application directories:
- Linux: `~/.local/share/personal‑finance‑sdd/`
- macOS: `~/Library/Application Support/Personal Finance SDD/`
- Windows: `%APPDATA%\Personal Finance SDD\`

**Non‑negotiable:** The application must not require write permissions outside these directories.
