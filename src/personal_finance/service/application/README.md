# service/application

Application services (BFF layer): screen-level facades that fulfil the data
contract of specific UI screens. These orchestrate one or more core services;
thin proxies are expected and acceptable.

UI screens must only import from this layer — never directly from `service/core/`.

## Services

- **`dashboard_service.py`** — Facade for the Dashboard screen (delegates to `GeneralService`).
- **`balance_sheet_app_service.py`** — BFF for the Balance Sheet Summary and Investment Editor screens.
- **`goal_app_service.py`** — BFF for the Goals screens.
- **`cash_flow_app_service.py`** — BFF for the Cash Flow screens.

## Key Constraints

- May call `service/core/` services; must not import from `ui/`.
- Logic that is not UI-specific belongs in `service/core/` instead.

## Session ownership (session-per-application-operation)

Application services own the SQLAlchemy session lifetime — this is the layer
that represents "one user-initiated action," which is the correct transaction
boundary. Each service is constructed with an injected `sessionmaker` (not a
live `Session`); every public method opens its own session for its entire
body via `db.transaction()` and passes that session into every core-service
call it makes:

```python
async def get_summary(self, as_of: date) -> BalanceSheetSummary:
    with transaction(self._session_factory) as session:
        accounts = await self._core.list_all_accounts(session, as_of)
        ...
        return BalanceSheetSummary(...)
```

`transaction()` commits on success and rolls back on any exception, so a
failure never leaves a dirty session behind — the next call opens a fresh one.
Core-service methods must never be called outside a `transaction()` block, and
core services never call `session.commit()`/`session.rollback()` themselves —
only the owning application-service method does, via `transaction()`.

Application-service methods that don't touch the database at all (e.g. simple
proxies with no core-service call) don't need `transaction()`. Methods whose
only core-service calls don't need a session (`search_symbols`, `get_unit_price`
— pricing is now cache-backed, not session-bound) also skip it.

See `specs/working-artefacts/adr/2026-07-28-backend-shared-session-transaction-safety.md`
for the full rationale, including why the session boundary sits here and not
one layer down inside `service/core/`.
