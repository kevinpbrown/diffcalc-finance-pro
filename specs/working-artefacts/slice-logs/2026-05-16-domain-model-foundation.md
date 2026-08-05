# Slice: Domain Model Foundation

**Date:** 2026-05-16
**Status:** Complete

## Description

This slice lays the foundational domain layer for the entire application. It is not a true vertical slice (no UI or service layer is touched), but it is a prerequisite for all future slices. Deliverables:

- All SQLAlchemy ORM models for every entity in the data requirements
- Domain-level business logic (Money timeline, GoalValue strategies, derived invariants)
- Database creation from the SQLAlchemy models (SQLite, schema-first)
- Comprehensive test suite for domain models and business logic

This slice covers the `domain/` layer only. No service or UI code is written.

## Specification References

### UI Flows to Implement

N/A — no UI flows are in scope for this foundational slice.

### Operations to Implement

N/A — no service operations are in scope for this foundational slice.

## Dependencies

- None (this is the first slice)

## ADRs

### Referenced
- None yet

### Created
- None yet

## TODOs

### Completed
- None

### Created
- None

## Decisions Made

- **SQLAlchemy mapped_column / DeclarativeBase** — use the SQLAlchemy 2.x `DeclarativeBase` + `mapped_column` style (not the legacy `Column` API) for full type-hint support and mypy compatibility.
- **Polymorphic inheritance strategy** — `Account`, `InvestmentAccountHolding`, and `GoalValue` each have subtypes. Use SQLAlchemy **single-table inheritance** for `GoalValue` (few columns, tight coupling) and **joined-table inheritance** for `Account` and `InvestmentAccountHolding` (distinct column sets per subtype).
- **Money as a relationship** — `Money` is modelled as a standalone table (`money_timelines`) with a one-to-many relationship to `money_entries`, rather than embedding entries directly on the owning entity.
- **Decimal storage** — monetary/percentage columns stored as `Numeric(precision=28, scale=10)` in SQLite to preserve `Decimal` semantics end-to-end.
- **Config-defined enumerations** — `InvestmentRegistration`, `SimpleAccountCategory`, `AccountClassification`, `MoneyEntrySource`, `HouseholdExpenseClassification`, `HouseholdExpenseSource`, `HouseholdExpenseFrequency` are Python `enum.Enum` types in source but their *display names / allowed values* are validated against the TOML config at startup.
- **No Alembic** — schema changes during development are handled by dropping and recreating the database. A `scripts/seed_db.py` script will handle seeding.
- **`Person` is static** — `Person` rows are seeded manually and never mutated through the application.
- **`AccountAssetClass.order_precedence`** — field exists in the domain diagram but was missing from the initial data requirements and code. Added in the Cash Flow slice review (2026-05-21).
- **`AccountAssetClass.dateDisabled` is intentional** — `AccountAssetClass` uses `dateDisabled` (not `dateDiscarded`) because it is a configuration object managed by the system, not a user-discardable entity. "Disabled" reflects a system state; "discarded" implies a user action.
- **`ListedSecurityHolding.quantity` uplifted to `EffectiveAmount`** — originally persisted as a scalar `Decimal`; corrected during the Balance Sheet service slice (2026-05-25) to use a temporal `EffectiveAmount` timeline, consistent with all other mutable domain values. The `quantity_id` FK and `relationship()` mirror the same pattern used by `ExactHolding.amount`.

## Uncertainties

- [x] Resolved: `HoldingAssetClassAllocation` invariant (sum = 100%) is enforced at the domain level only via `InvestmentAccountHolding.validate_allocations(as_of)`. No DB check constraint. Service layer must call this before persisting allocation changes.
- [x] Resolved: `GoalAssetClassTarget` sums do not need to equal 100%. No constraint is enforced at any layer. UI will show a warning if the sum exceeds 100%.
- [x] Resolved: `Money.offerValue` always inserts a new entry, never replaces. Multiple entries may share an `effectiveDate`; the one with the highest `sequence` is authoritative. `sequence` is unique per timeline (enforced by DB unique constraint on `timeline_id, sequence`).
- [x] Resolved: `autoRrspGoal` on `PersonalCashFlowProfile` is a **nullable FK** to `Goal`. The service layer must reject any save where `autoRrspDeducted` or `rrspMatched` have entries > 0 but `autoRrspGoal` is null. DB-level NOT NULL is not useful because the constraint on the temporal Money values can only be evaluated at the service layer.

## Handoff Notes

- All subsequent slices build on this domain layer. The service layer should never bypass these models.
- `scripts/seed_db.py` (created in this slice) must be kept in sync as the schema evolves.
- The `ListedSecurityHolding` has a `symbol` and `quantity` but no price fetching in this slice — market value is a concern for a later slice (price provider integration).
- Next recommended slice: Balance Sheet service layer + read-only TUI screen.

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
