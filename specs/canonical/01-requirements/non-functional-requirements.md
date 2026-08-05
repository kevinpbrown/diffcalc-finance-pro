# Non-Functional Requirements

This document defines performance, security, usability, and other quality attributes for the Personal Finance Textual UI system.

## Usability

### U‑1: Learnability
**A user familiar with the original Excel spreadsheet shall be able to perform basic operations (view balance sheet, update an account balance) within 5 minutes of first use, without external documentation.**

- **Rationale:** The system replaces an existing manual process; the learning curve should be minimal.
- **Measurement:** Observation of new users completing a set of predefined tasks.
- **Notes:** The UI shall follow Textual conventions (keyboard navigation, clear menus, contextual help).

### U‑2: Accessibility
**The Textual UI shall be fully operable with keyboard-only input and shall support screen‑reader compatibility where the terminal environment allows.**

- **Rationale:** Users may have different accessibility needs; the application should not rely solely on mouse interaction.
- **Measurement:** All functions can be reached and executed via keyboard shortcuts or menu navigation.
- **Notes:** Color choices shall provide sufficient contrast for common terminal themes.

### U‑3: Error Handling
**User input errors shall be caught and reported with clear, actionable messages that explain what went wrong and how to correct it.**

- **Rationale:** Financial data is sensitive; users must understand why an operation failed and how to proceed.
- **Measurement:** Review of error messages for clarity and helpfulness.
- **Notes:** Validation errors should be highlighted inline where possible (e.g., next to the invalid field).

### U‑4: Data Visibility
**All important financial totals (net worth, monthly retained, goal progress) shall be visible on the main dashboard or retrievable with a single command.**

- **Rationale:** Users need quick access to key metrics without navigating deep menus.
- **Measurement:** Number of keystrokes/clicks required to see each metric from the main screen.
- **Notes:** The dashboard should be customizable (user can choose which metrics to display).

## Reliability & Availability

### R‑1: Data Integrity
**The system shall guarantee that all committed changes are persisted and survive an application crash or system shutdown.**

- **Rationale:** Financial data must not be lost due to power loss or unexpected termination.
- **Measurement:** After forced termination during a write operation, restarting the application must show either the old state or the new state, never a corrupted intermediate state.
- **Notes:** Use of a transactional database (SQLite) with proper commit/rollback is recommended.

### R‑3: Uptime
**The application shall be available for use whenever the host system is running, with no external dependencies that could cause unavailability.**

- **Rationale:** As a desktop application, it should not rely on network services for core functionality.
- **Measurement:** The application can be launched and used offline indefinitely.
- **Notes:** Optional features that require network access (e.g., fetching stock prices) shall degrade gracefully when offline.

## Maintainability & Extensibility

### M‑1: Modular Design
**The codebase shall be organized into three independent primary modules (balance_sheet, goals, cash_flow) with well‑defined interfaces, allowing independent development and testing.**

- **Rationale:** Future enhancements or bug fixes should be localized to the relevant module. Modules must remain as independent as possible with clear interfaces defined where they interact to minimize coupling.
- **Measurement:** Cyclomatic complexity and coupling metrics meet industry standards for maintainable Python code.
- **Notes:** Dependencies between modules shall be strictly unidirectional (`goals` -> `balance_sheet`; `cash_flow` -> `goals` & `balance_sheet`).

### M‑2: Configuration Over Code
**Household-specific values that genuinely vary between users (owner identifiers, asset class names, numeric tunables) shall be defined in TOML configuration, not hard-coded in source.**

- **Rationale:** Adding a new owner or asset class is a per-household concern, not a code change.
- **Measurement:** Adding a new owner or asset class name requires only a configuration edit.
- **Notes:** Domain enumerations whose value sets are fixed by the financial domain (account classifications, investment registration types, expense classifications/sources/frequencies) are intentionally hard-coded as Python enums; extending them is a deliberate design decision. See the technical charter's *Configuration-Over-Code* section for the authoritative list.

### M‑3: Logging
**The application shall produce structured logs at different severity levels (DEBUG, INFO, WARN, ERROR) to aid debugging and monitoring.**

- **Rationale:** When something goes wrong, logs must provide enough context to diagnose the issue.
- **Measurement:** Logs include timestamps, module names, and relevant identifiers (account ID, user session).
- **Notes:** Logs may be written to a file, stdout, or both, configurable by the user.

### M‑4: Testing & Quality Standards
**The system shall have a comprehensive test suite covering at least 80% of the domain and service layers, and all vertical slices must pass linting and type-checks.**

- **Rationale:** Confidence in correctness is paramount for financial software. Enforcing strict testing and linting standards prevents regressions.
- **Measurement:** >80% code coverage on domain/service modules. A reasonable baseline is established for UI modules. `mypy` and standard linters return zero errors on each PR/slice close.
- **Notes:** Testing must be confirmed prior to closing a vertical slice.

## Compatibility

### C‑1: Platform Support
**The application shall run on Linux, macOS, and Windows (via WSL or native Python) with consistent behaviour.**

- **Rationale:** Users may have diverse desktop environments.
- **Measurement:** The test suite passes on all three platforms (or emulated environments).
- **Notes:** Platform‑specific features (e.g., system keychain) may have fallbacks.

### C‑2: Terminal Compatibility
**The UI shall render correctly in terminals that support ANSI escape codes (most modern terminals) and degrade gracefully for older terminals.**

- **Rationale:** Users may choose different terminal emulators (iTerm2, Windows Terminal, GNOME Terminal, etc.).
- **Measurement:** Visual inspection on a representative set of terminals.
- **Notes:** Feature detection may be used to disable advanced formatting when unsupported.
