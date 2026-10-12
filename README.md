# ProofFlow — Evidence Intelligence Platform

> Turn scattered evidence into a structured, traceable understanding of what happened.

ProofFlow is a full-stack incident-evidence workspace designed to organize documents, screenshots, receipts, statements, and correspondence into a more structured view of an incident. The project explores evidence extraction, timeline reconstruction, and surfacing potential inconsistencies while keeping the underlying evidence traceable.

## ✨ What it focuses on

- **Evidence organization:** bring different evidence types into one case workspace.
- **Timeline reconstruction:** structure events so their sequence is easier to review.
- **Inconsistency review:** highlight details that may need closer human inspection.
- **Identity-aware access:** authenticate users and isolate their case data.
- **Evaluation-first development:** maintain tests and evaluation tooling around core workflows.

> ProofFlow is a work in progress. Treat extracted insights as review aids, not as a substitute for human judgment or formal legal advice.

## 🧱 Architecture & technology

| Area | Technologies |
| --- | --- |
| Web application | Next.js, TypeScript, Tailwind CSS v4 |
| Client data & state | TanStack Query, Zustand |
| API | Python, FastAPI, Pydantic |
| Database access | PyMongo AsyncMongoClient |
| Authentication | Clerk, RS256 JWT verification using JWKS |
| Testing & evaluation | Pytest, Vitest, evidence evaluation suites |

## 📁 Repository layout

- `apps/api/` — FastAPI backend and API tests
- `apps/web/` — Next.js frontend
- `packages/shared/` — shared schemas, constants, and utilities
- `ml/` — evidence extraction pipelines and evaluation experiments
- `infra/` — infrastructure and deployment configuration
- `docs/` — architecture specifications and API documentation
- `tests/` — integration test suites

## 🔐 Authentication and local configuration

The frontend uses Clerk for user management. The API verifies session tokens using RS256 and Clerk's JWKS endpoint.

### Frontend: `apps/web/.env.local`

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_placeholder
CLERK_SECRET_KEY=sk_test_placeholder
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/
```

### Backend: `apps/api/.env` or the configured root environment file

```bash
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_AUDIENCE=
CLERK_AUTHORIZED_PARTIES=http://localhost:3000
ALLOW_DEV_AUTH_BYPASS=false
AUTH_JWKS_CACHE_TTL_SECONDS=300
AUTH_JWKS_TIMEOUT_SECONDS=10
```

Replace placeholder values with your own development credentials and issuer details.

**Security notes**
- Never commit real secrets or expose `CLERK_SECRET_KEY` to the browser.
- Keep `ALLOW_DEV_AUTH_BYPASS=false` unless you intentionally need the documented development/test bypass.
- Production must use HTTPS, correct CORS origins, and matching authorized-party settings.
- In production, the application is designed to fail startup if the development auth bypass is enabled; client-supplied `X-User-ID` must not be trusted.

### Development identity note

Older development fixtures may belong to `dev_user_default`. A newly authenticated Clerk account has its own identity and may not see those fixtures. Use the documented development/test bypass only in a local, non-production environment when needed.

## 🧪 Tests

The repository's documented test suites can run without real Clerk credentials by using synthetic keys and mocked token providers:

```powershell
$env:PYTHONPATH="apps/api;."
apps/api/.venv/Scripts/pytest apps/api/tests
npm run test --prefix apps/web
```

The repository README previously documented 100 backend tests and 34 frontend tests; test counts may change as the project evolves.

## 🚧 Project status

The architecture/specification phase and the authentication identity-hardening track have been documented as complete. Evidence workflows and evaluation capabilities remain part of the ongoing development effort.

## 🗺️ Roadmap ideas

- Expand supported evidence formats and extraction checks
- Improve explainability around timeline conflicts
- Add representative evaluation datasets and regression checks
- Strengthen deployment documentation and operational monitoring

---

Built as a software engineering project exploring evidence workflows, full-stack architecture, and responsible AI-assisted review.
