# ProofFlow

Evidence Intelligence Web Application.

> "Turn scattered evidence into a structured, traceable understanding of what happened."

## Project Overview

ProofFlow is a full-stack incident evidence intelligence workspace. It ingests multi-modal evidence (documents, receipts, screenshots, statements, correspondence), extracts structured data, and reconstructs verifiable incident timelines while highlighting potential inconsistencies.

## Monorepo Structure

- `apps/api/`: FastAPI Backend service (PyMongo AsyncMongoClient, Pydantic)
- `apps/web/`: Next.js Web Application (TypeScript, Tailwind CSS v4, TanStack Query, Zustand)
- `packages/shared/`: Shared schemas, constants, and utilities
- `ml/`: Evidence extraction pipelines, evaluation suites, and experimental notebooks
- `infra/`: Infrastructure definitions and deployment configurations
- `docs/`: Architecture specifications and API documentation
- `tests/`: End-to-end integration test suites

## Status

Phase 0: Architecture & Specification (Complete & Locked)  
Track 7A: Authentication & Identity Hardening (Complete)

## Authentication & Security Setup (Track 7A)

ProofFlow uses **Clerk** for user management on the frontend and **RS256 JWKS JWT Verification** on the FastAPI backend.

### 1. Clerk Development Instance Setup

1. Create a free development application at [clerk.com](https://clerk.com).
2. Set up User Authentication (Email/Password, Google OAuth, etc.) with open registration.
3. Retrieve your **Publishable Key** (`pk_test_...`) and **Secret Key** (`sk_test_...`) from the Clerk Dashboard API Keys section.

### 2. Frontend Configuration (`apps/web/.env.local`)

Configure the following public keys in `apps/web/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_placeholder
CLERK_SECRET_KEY=sk_test_placeholder
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/
```

*Note: Never commit real keys or expose `CLERK_SECRET_KEY` on the client.*

### 3. Backend Configuration (`apps/api/.env` or root `.env`)

Configure the backend to cryptographically verify Clerk session tokens:

```bash
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_AUDIENCE=
CLERK_AUTHORIZED_PARTIES=http://localhost:3000
ALLOW_DEV_AUTH_BYPASS=false
AUTH_JWKS_CACHE_TTL_SECONDS=300
AUTH_JWKS_TIMEOUT_SECONDS=10
```

### 4. Development Identity Bypass & Existing `dev_user_default` Data

- In development/test mode, setting `ALLOW_DEV_AUTH_BYPASS=true` enables local developers and scripts to inject `X-User-ID` or fall back to `dev_user_default` without logging into Clerk.
- Existing cases created during earlier phases belong to `dev_user_default` and are preserved intact. When signed in as a newly registered Clerk user (`user_2...`), your private cases are isolated to your Clerk identity. To continue accessing development fixtures, run with `ALLOW_DEV_AUTH_BYPASS=true` or query via development bypass.
- **Production Guardrail:** If `ENVIRONMENT=production`, setting `ALLOW_DEV_AUTH_BYPASS=true` causes an immediate fatal startup error. Production strictly mandates verified RS256 Bearer tokens and rejects client-supplied `X-User-ID`.

### 5. Running Tests Without Real Credentials

All automated tests run completely offline without real Clerk credentials or external network access:

```bash
# Backend pytest suite (100 tests with synthetic RSA key pairs)
$env:PYTHONPATH="apps/api;."; apps/api/.venv/Scripts/pytest apps/api/tests

# Frontend Vitest suite (34 tests with mocked token provider)
npm run test --prefix apps/web
```

### 6. Production Deployment Requirements

- Production requires HTTPS/TLS encryption.
- CORS origins (`CORS_ORIGINS`) and authorized parties (`CLERK_AUTHORIZED_PARTIES`) must match production frontend domains.
- `ALLOW_DEV_AUTH_BYPASS` must remain `false`.
