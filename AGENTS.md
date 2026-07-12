# Pharmacy System Project Rules

## 1. Project Context
*   **Purpose:** A pharmacy management backend built with FastAPI.
*   **Architecture:** We use a modular structure. Database models are separate from API routes.

## 2. Mandatory Agent Workflow (DO NOT SKIP)
When the user asks you to add a feature or debug, you MUST execute these steps in order:
1.  **Reconnaissance:** Do not guess file structures. Use your Read tools to open and scan `main.py`, the routing folder, and the database models folder to understand the current state.
2.  **The Plan:** Write out a bulleted, step-by-step implementation plan in the chat. Explain *how* the new code will interact with the existing code.
3.  **Execution:** Use your Edit tools to write the code. Do not break existing functionality.
4.  **Verification:** Check your work for syntax errors before presenting the final result.

## 3. Coding Standards
*   Always use asynchronous functions (`async def`) for FastAPI routes.
*   Handle database errors gracefully without crashing the app.
*   Write explicit Pydantic schemas for all inputs and outputs.