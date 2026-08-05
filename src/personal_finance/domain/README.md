# domain

The domain layer contains all business logic, SQLAlchemy models, validation rules, and decimal arithmetic. It is framework-agnostic and has no dependencies on the service or UI layers.

## Submodules

- **`balance_sheet/`** — Account and holding models; net worth calculations.
- **`goals/`** — Goal models and allocation logic. May reference `balance_sheet` entities.
- **`cash_flow/`** — Projection models and income/expense logic. May reference `balance_sheet` and `goals` entities.

## Key Constraints

- Use `decimal.Decimal` (never `float`) for all monetary values and percentages.
- Domain entities are immutable once persisted; updates produce a new record with an updated `updated_at` timestamp.
- No dependency on `service` or `ui` layers.
