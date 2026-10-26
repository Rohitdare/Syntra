# Contracts

This folder contains shared JSON contract fixtures used to verify wire compatibility between the backend (`apps/api`) and frontend (`apps/web`).

## Purpose
- Prevent silent schema drift between FastAPI (Pydantic models) and Next.js (Zod schemas).
- Every fixture here is validated by:
  - **Pytest** in `apps/api/tests/test_contract.py` using Pydantic models in `core/schemas.py`.
  - **Vitest** in `apps/web/tests/contracts.test.ts` using Zod schemas in `src/lib/api/schemas.ts`.

## Naming Convention
- Request/response fixtures: `<resource>.json` or `<resource>_<action>.json` (e.g. `health.json`).
- Errors: `error.json` (or `error_<code_category>.json`).
- Events: `event_<type>.json`.
- All JSON keys must follow camelCase wire format.
