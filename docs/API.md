# API Reference

Every endpoint, its request shape, its response shape, and its error
codes. All endpoints are under `/api/v1/`.

**Authentication:** unless noted, every endpoint requires a logged-in
session. Unauthenticated requests receive `401 Unauthorized`.

**Money:** all monetary values in JSON are **strings** (e.g. `"250.00"`),
never numbers. This preserves precision — see
[DECISIONS.md](DECISIONS.md#adr-001).

**Errors:** errors always look like:

```json
{ "errors": ["human-readable message", "..."] }
