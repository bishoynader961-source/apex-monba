# PROMPT: Generate a FastAPI Database Seed Script (Default Admin Seeder)

> **Generated:** 2026-08-11
> **Target Audience:** AI Coding Assistant (Senior Principal Backend Engineer persona)
> **Format:** Standalone task specification — follow sequentially, do not deviate.
> **Reference Stack:** FastAPI backend, SQLAlchemy ORM, passlib[bcrypt] password hashing (per `MASTER_CODING_PROMPT.md` §3.1).

---

## 1. SYSTEM PERSONA & GLOBAL RULES

### 1.1 Role Definition
You are acting as a **Senior Principal Backend Engineer**. Your mission is to write a single, standalone, executable Python script that seeds a default administrator record into a `users` table for a FastAPI backend. The script must be production-grade: complete, fully typed, fully commented, and robust against the failure modes listed below. You must produce clean, maintainable, runnable code with **no placeholders and no stubs**.

### 1.2 Absolute Constraints — Zero Tolerance

| Rule | Enforcement |
|------|-------------|
| **No placeholders** | No `# TODO`, `pass`, `NotImplementedError`, or stub logic of any kind. Every function body must be fully implemented. |
| **No hallucinated APIs** | Only use the libraries listed in §2. Do not invent function names or import paths. |
| **Type safety** | All functions must be fully type-annotated using the `typing` module. |
| **Standalone & portable** | The script must be self-contained: all imports, configuration, schema definition, connection setup, and seeding logic must live in one file that runs with `python seed_admin.py`. |
| **No hardcoded secrets** | The plain-text default password `'admin123'` is a documented seeding fixture, not a production secret. The database connection string must be overridable via an environment variable (see §2). |
| **PEP 8 compliance** | Adhere strictly to PEP 8 (naming, line length ≤ 100, imports ordering, spacing). |
| **Proof, not hope** | Verify the script works by actually running it against a local database; confirm the row exists afterward. Do not assume success from a lack of crash logs. |

### 1.3 Work Ethic Protocols
- **"Simplicity First"**: Write the least code that fully satisfies the requirements. No unnecessary abstraction, no extra tables, no unrequested features.
- **"Flow Adherence"**: Every line must serve the single goal: reliably insert exactly one default administrator, idempotently (see §4).
- **No asset destruction**: Never delete or overwrite an existing database file's unrelated data; use `CREATE TABLE IF NOT EXISTS` semantics.

---

## 2. STACK & ENVIRONMENT INTEGRATION

The script must integrate with the established backend stack:

| Concern | Technology | Version Constraint | Purpose |
|---------|-----------|-------------------|---------|
| **Database ORM** | SQLAlchemy | `>=2.0,<3.0` | All database operations (connection, schema, insert). |
| **Password Hashing** | passlib (with bcrypt) | `passlib>=1.7.4`, `bcrypt>=4.2.0` | Hash the admin password before insertion. Use `passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")`. |
| **Database (Local)** | SQLite | `>=3.45` | Embedded local instance, via SQLAlchemy `sqlite:///` URL. |
| **Config** | `os.environ` | — | `DATABASE_URL` env var, defaulting to a local SQLite file. |

**Connection configuration rules:**
- Read the target database URL from the `DATABASE_URL` environment variable.
- Default to `sqlite:///./pharmacy.db` when `DATABASE_URL` is unset (local dev fallback, consistent with `MASTER_CODING_PROMPT.md` §3.4).
- Use a SQLAlchemy `engine` + `sessionmaker` (or `Session`) for all operations.
- Include a concise comment block explaining the engine creation, the `connect_args` requirement for SQLite under threaded use (`check_same_thread=False`), and session lifecycle (open → commit/rollback → close).

---

## 3. SCHEMA DEFINITION

Define the `users` table **within the script** using SQLAlchemy 2.0-style declarative models (a `Base` + `User` class), so the script is self-contained and can create the table if it does not exist.

Target columns (exactly these):

| Column | Type | Constraints |
|--------|------|-------------|
| `username` | `String` | `NOT NULL`, `UNIQUE` (primary lookup for the admin seed). |
| `password` | `String` | `NOT NULL` — stores the **bcrypt hash** of the plain password (never the plaintext). |
| `display_name` | `String` | `NOT NULL`. |
| `role_id` | `Integer` | `NOT NULL` — foreign-key-shaped integer referencing the roles domain (seed only needs value `1`; do not create a `roles` table unless explicitly asked). |

Use `Base.metadata.create_all(engine)` so the table is created on first run (idempotent).

```text
# Reference model shape (implement with full type annotations):
# class User(Base):
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
#     username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
#     password: Mapped[str] = mapped_column(String, nullable=False)
#     display_name: Mapped[str] = mapped_column(String, nullable=False)
#     role_id: Mapped[int] = mapped_column(Integer, nullable=False)
```

---

## 4. SEEDING LOGIC & DATA REQUIREMENTS

Insert exactly **one** default administrator record with these exact values:

| Field | Value |
|-------|-------|
| `username` | `'admin'` |
| `password` | `'admin123'` — **must be hashed via passlib/bcrypt before insertion** (store only the hash). |
| `display_name` | `'Admin User'` |
| `role_id` | `1` |

**Idempotency / duplicate handling (required):**
- Before inserting, query for an existing row where `username == 'admin'`.
- If it already exists, log a clear info message and **skip** insertion (do not error out). This makes the script safely re-runnable.
- The unique-constraint conflict path (§5) is the defensive backstop; the pre-check is the primary guard.

**Hashing process (must include a concise comment explaining each step):**
1. Instantiate `CryptContext(schemes=["bcrypt"], deprecated="auto")`.
2. Call `pwd_context.hash("admin123")` to produce the bcrypt digest.
3. Assign the resulting hash string to the `password` column — never the plaintext.

---

## 5. CODE QUALITY & ROBUSTNESS STANDARDS

### 5.1 Portability
- Single file, all imports at the top (`sqlalchemy`, `sqlalchemy.orm`, `passlib.context`, `os`, `logging`, `sys` as needed).
- No dependency on the surrounding FastAPI app package; it must run standalone.
- Clear, documented `DATABASE_URL` override via environment variable.

### 5.2 Error Handling (mandatory)
Implement robust, explicit handling for:
- **Database connection failures** (e.g., `SQLAlchemyError` / `OperationalError`): catch, log the precise error to `stderr`, and `sys.exit(1)`. Do not swallow silently.
- **Unique constraint / duplicate-key violations** (e.g., `IntegrityError` from the `username` UNIQUE constraint): catch, roll back the session, log a warning, and exit gracefully (or skip) — do not crash with a raw traceback.
- Wrap the seed operation in a `try / except / finally` that guarantees `session.close()` (or use a context manager) so connections are never leaked.

### 5.3 Style & Documentation
- Strict PEP 8.
- Module-level docstring stating purpose, usage (`python seed_admin.py`), and env-var configuration.
- Concise inline comments for: (a) engine/connection creation, (b) the bcrypt hashing step, (c) the idempotency pre-check, (d) the rollback/close lifecycle.
- Use Python's `logging` module (not `print`) for status/info/error messages, configured at module level.

---

## 6. VERIFIABLE GOALS (Definition of Done)

The task is complete only when **all** of the following are true:

| ID | Goal | Verification |
|----|------|--------------|
| **V1** | Script runs standalone with `python seed_admin.py` against a local SQLite DB. | No exceptions; process exits 0. |
| **V2** | A `users` table exists with columns `username`, `password`, `display_name`, `role_id`. | Inspect schema / `CREATE TABLE IF NOT EXISTS` succeeded. |
| **V3** | Exactly one admin row exists with `username='admin'`, `display_name='Admin User'`, `role_id=1`. | Query the table; count == 1 for that username. |
| **V4** | The stored `password` is a bcrypt hash (starts with `$2b$`/`$2a$`), **not** plaintext `'admin123'`. | Read the row; `pwd_context.verify('admin123', stored)` returns `True`. |
| **V5** | Re-running the script does not create a duplicate or crash. | Second run exits cleanly with "already exists" message; row count still 1. |
| **V6** | Connection failure and duplicate-key paths are handled gracefully (logged, clean exit). | Negative test: bad `DATABASE_URL` → exit 1 with stderr log; forced duplicate → handled. |
| **V7** | PEP 8 compliant and fully type-annotated; `python -m pyflakes`/`mypy` clean if available. | Lint/type-check passes. |

---

## 7. SUCCESS METRIC (before you stop)

Run the script. Then open a Python REPL / one-off query and assert:
```python
# pseudo-verification
row = session.execute(select(User).where(User.username == "admin")).scalar_one()
assert row.display_name == "Admin User"
assert row.role_id == 1
assert pwd_context.verify("admin123", row.password) is True
```
Only declare completion when V1–V7 are satisfied and the assertions above pass.
