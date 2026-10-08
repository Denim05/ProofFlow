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
Phase 1: Foundation Implementation (In Progress)
