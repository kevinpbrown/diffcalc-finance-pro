# service

The service layer sits between the domain and UI layers. It is the only layer
the UI may call; it in turn calls the domain layer.

The layer is split into two sub-layers:

## core/

Reusable domain operations that map to named operations in the
service-operations spec. These must be independently testable without Textual
and must contain no screen-specific logic. See [`core/README.md`](core/README.md).

## application/

Screen-level facades (BFF pattern) that fulfil specific screens' data contracts
by orchestrating core services. UI screens import exclusively from this
sub-layer. See [`application/README.md`](application/README.md).

## Key Constraints

- UI screens must only import from `service/application/`.
- `service/core/` must not import from `service/application/` or `ui/`.
- No direct database access that bypasses SQLAlchemy models.
- No business logic that belongs in the domain layer.
