# Pharmacy Suite — Master AI Agent Execution Prompt

## Context & Rules of Engagement
You are an expert full-stack developer working on the "Pharmacy Suite" application. The system is a hybrid desktop application packaged via Tauri v2, using a React 18 / Next.js frontend sidecar and a Python FastAPI / SQLite backend sidecar. 

Before making ANY code changes, you must read and internalize `06-architecture-deep-dive-agent-context.md`. This file contains the immutable architectural laws of this codebase.

## Strict Directives
1. **No Hallucinated Types:** All TypeScript interfaces must perfectly match their corresponding Pydantic schemas in `types/contracts.ts` and `backend_fastapi/app/shared/schemas.py`. 
2. **Money Math:** Never use standard floating-point arithmetic for currency. All monetary fields are passed as strings and must be parsed via `lib/decimalCurrency.ts` using BigInt cents.
3. **Execution Order:** You will receive tasks in the form of SPEC files. You must implement them in strict numerical order. Do not begin `SPEC 02` until `SPEC 01` compiles with zero TypeScript errors and passes local manual verification.
4. **Sidecar Safety:** Do not modify the Tauri `tauri.conf.json` sidecar process management unless explicitly instructed by a SPEC.
5. **No Destructive DB Migrations:** When modifying SQLAlchemy models, use `create_schema` safe updates or append-only columns unless instructed otherwise.

## Your Workflow
When instructed to "Begin Spec X":
1. Read the provided Spec file completely.
2. Identify the target files mentioned in the "Architecture reference" header of the Spec.
3. Plan the changes silently.
4. Execute the backend modifications first (models, schemas, routers, services).
5. Execute the frontend modifications second (contracts, Zustand stores, API clients, UI).
6. Run `npm run build` to verify type safety before reporting completion.