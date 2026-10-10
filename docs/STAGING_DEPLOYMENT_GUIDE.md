# ProofFlow — Staging Deployment Guide

This guide describes the operational architecture, prerequisites, configuration, and step-by-step deployment procedure for running ProofFlow in a staging environment.

---

## 1. Architectural Model & Persistence Strategy

### Single Backend Instance Rationale

ProofFlow is designed to be deployed to staging as a **single backend instance** backed by a **persistent volume**:

1. **Persistent Evidence Storage:**
   - Evidence documents (`.pdf`, `.png`, `.jpg`) uploaded by users are saved to the POSIX directory `/app/storage/evidence` (`settings.EVIDENCE_STORAGE_DIR`).
   - Ephemeral container filesystems (common on free-tier platforms) destroy stored files upon container sleep, scale-to-zero, or redeployment.
   - A single backend instance with a mounted block volume guarantees all uploaded evidence remains intact and accessible for reprocessing, Cross-Examination comparison, and Dossier generation.

2. **In-Memory Rate Limiting:**
   - Evidence upload rate limiting (30 requests/minute) and PDF export rate limiting (10 requests/minute) use sliding-window in-memory tracking per tenant user ID.
   - A single instance maintains consistent rate limits without requiring a distributed cache (e.g. Redis).

3. **In-Flight File Cleanup Safety:**
   - Active upload temporary files (`storage/temp`) are protected in-process via `_active_temp_paths` locks during chunk streaming.
   - Single-process execution prevents race conditions between background cleanup tasks and concurrent uploads.

> [!NOTE]
> **Future Multi-Instance Scaling:** Transitioning to multiple stateless backend replicas in the future will require migrating evidence storage to an object store (e.g. AWS S3 or GCP Cloud Storage) and migrating in-memory rate limiting to Redis. For staging, the single-instance persistent volume pattern is the simplest, most reliable, and lowest-cost architecture.

---

## 2. Recommended Hosting Options & Estimated Costs

All costs listed below are estimated market rates as of late 2024 / 2026.

| Hosting Strategy | Architecture | Estimated Monthly Cost | Pros & Cons |
| :--- | :--- | :--- | :--- |
| **Option A (Recommended PaaS)**: Render Standard + MongoDB Atlas M0 | API: Render Web Service (Starter)<br>Disk: Render Persistent Disk (3GB)<br>Web: Render Web Service or Vercel Hobby<br>DB: MongoDB Atlas M0 (Free Tier) | **~$8.00 – $14.00 / month**<br>*(API: $7/mo, Disk: $1/mo, Web: $0–$7/mo, DB: $0)* | **Pros:** Fully managed, automatic TLS/SSL, Git-push deployments.<br>**Cons:** PaaS persistent disks incur monthly charges (free tiers do NOT support disks). |
| **Option B (Recommended VPS)**: Single Linux VM with Docker Compose | VM: Hetzner Cloud CX22 or DigitalOcean Droplet (2GB RAM, 1 vCPU)<br>Reverse Proxy: Caddy with auto Let's Encrypt<br>DB: MongoDB Atlas M0 (Free Tier) | **~$4.00 – $12.00 / month**<br>*(Hetzner: ~€3.79/mo ≈ $4.10, DO: $12/mo, Atlas: $0)* | **Pros:** Full host control, native host SSD volume mounts, both services co-located, zero egress fees.<br>**Cons:** Requires basic Linux server maintenance. |
| **Option C (Free Tier Traps)**: Render Free / Railway Trial / Heroku | Ephemeral container filesystem<br>No persistent disks on free tier | **$0.00 / month (Unsuitable for Staging)** | **UNSUITABLE:** Containers wipe evidence files on sleep/restart; upload and dossier generation fail. |

---

## 3. Deployment Prerequisites & Manual Dashboard Actions

Before deploying, you must provide the following infrastructure and configuration values from external dashboards. **Antigravity cannot and will not invent real credentials or domain names.**

### A. MongoDB Atlas (Staging Database)

1. Log in to [MongoDB Atlas](https://cloud.mongodb.com/).
2. Create or select a project (e.g., `ProofFlow-Staging`).
3. Deploy a free **M0 Sandbox Cluster** (AWS or GCP region closest to your host).
4. Under **Database Access**, create a dedicated database user (e.g. `proofflow_staging_user`) with `readWrite` permissions on database `proofflow_staging`.
5. Under **Network Access**, add the IP address of your staging server (or `0.0.0.0/0` with strong password authentication if using dynamic cloud PaaS IP pools).
6. Click **Connect -> Drivers -> Python** to obtain your connection URI:

   ```text
   mongodb+srv://<username>:<password>@<staging-cluster>.mongodb.net/?retryWrites=true&w=majority
   ```

### B. Clerk Authentication (Staging Instance)

1. Log in to the [Clerk Dashboard](https://dashboard.clerk.com/).
2. Create or select a dedicated Staging Application (or Development Instance for staging testing).
3. Under **API Keys**:
   - Copy the **Publishable Key** (`pk_test_...` or `pk_live_...`).
   - Copy the **Secret Key** (`sk_test_...` or `sk_live_...`).
4. Under **JWT Templates** / **Configure -> Domains & URLs**:
   - Identify the **Frontend API / Issuer URL** (e.g. `https://clerk.your-domain.dev` or `https://<app-id>.clerk.accounts.dev`).
   - Identify the **JWKS URL**: typically `https://<issuer>/.well-known/jwks.json`.
   - Add your Staging Frontend domain (e.g. `https://staging.proofflow.example.com`) to **Allowed Origins**.
5. Note your exact frontend staging URL to provide as `CLERK_AUTHORIZED_PARTIES`.

### C. Domain Names & DNS

1. Choose DNS hostnames for staging:
   - Frontend: `https://staging.proofflow.yourdomain.com`
   - Backend API: `https://api-staging.proofflow.yourdomain.com`
2. Point DNS `A` or `CNAME` records to your staging host or PaaS service.

---

## 4. Environment Variables Reference

Create `infra/.env.staging` (or set environment variables in your hosting provider's dashboard). **Never commit this file to Git.**

| Variable | Target Service | Required Value / Source | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | API | `staging` | Strictly set to `staging`. Prohibits dev bypass. |
| `SERVICE_NAME` | API | `ProofFlow API` | Service display name. |
| `API_SECRET_KEY` | API | Generated 32+ byte hex string | Generate with `openssl rand -hex 32`. |
| `MONGODB_URI` | API | `mongodb+srv://...` | MongoDB Atlas staging connection URI. |
| `MONGODB_DATABASE` | API | `proofflow_staging` | Staging database name. |
| `CORS_ORIGINS` | API | `https://staging.proofflow.yourdomain.com` | Comma-separated list of allowed frontend origins. |
| `CLERK_ISSUER` | API | `https://...clerk.accounts.dev` | Clerk staging issuer URL. |
| `CLERK_JWKS_URL` | API | `https://...clerk.accounts.dev/.well-known/jwks.json` | Clerk JWKS public keys URL. |
| `CLERK_AUTHORIZED_PARTIES` | API | `https://staging.proofflow.yourdomain.com` | Verified `azp` claim matching frontend origin. |
| `ALLOW_DEV_AUTH_BYPASS` | API | `false` | **MUST BE FALSE.** Startup fails if `true`. |
| `EVIDENCE_STORAGE_DIR` | API | `/app/storage/evidence` | Mount path for persistent evidence volume. |
| `TEMP_STORAGE_DIR` | API | `/app/storage/temp` | Temporary processing scratch path. |
| `TRUSTED_PROXIES` | API | `127.0.0.1` or reverse proxy IP | Trusted IPs allowed to supply `X-Forwarded-For`. |
| `NEXT_PUBLIC_API_URL` | Web & API | `https://api-staging.proofflow.yourdomain.com` | Public HTTPS backend URL accessed by client. |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Web | `pk_test_...` | Clerk public key for browser SDK. |
| `CLERK_SECRET_KEY` | Web | `sk_test_...` | Clerk private key for server-side middleware. |
| `NODE_ENV` | Web | `production` | Enables Next.js production optimizations. |

---

## 5. Storage Mounts & Health Check Endpoints

### Storage Mount Paths

| Mount Target | Purpose | Host / Volume Mapping |
| :--- | :--- | :--- |
| `/app/storage/evidence` | Durable Evidence Storage | Named Docker volume `proofflow_evidence_data` or persistent host directory `/opt/proofflow/storage/evidence` |
| `/app/storage/temp` | Temporary Upload Scratch | Container-local directory (automatically swept on startup) |

### Health Check Probes

- **Backend API Health Probe:**
  - Route: `GET /health` or `GET /api/v1/health`
  - Port: `8000`
  - Success Response: `200 OK`

    ```json
    {
      "status": "healthy",
      "database": "connected",
      "service": "ProofFlow API",
      "version": "0.1.0"
    }
    ```

  - Unhealthy Response: `503 Service Unavailable` (`"database": "disconnected"`)

- **Frontend Web Health Probe:**
  - Route: `GET /health`
  - Port: `3000`
  - Unauthenticated route configured in `middleware.ts`
  - Success Response: `200 OK` (`{"status": "healthy", "service": "ProofFlow Web"}`)

---

## 6. Step-by-Step Deployment Instructions

### Workflow 1: Docker Compose on a Linux VM (Option B)

1. **Provision VM and Install Docker:**

   ```bash
   ssh root@<staging-server-ip>
   apt-get update && apt-get install -y docker.io docker-compose git
   ```

2. **Clone Repository and Configure Staging Environment:**

   ```bash
   git clone <your-private-repo-url> /opt/proofflow
   cd /opt/proofflow
   cp infra/.env.staging.example infra/.env.staging
   nano infra/.env.staging
   # Fill in real MongoDB Atlas URI, Clerk Keys, API_SECRET_KEY, and HTTPS domains.
   ```

3. **Build and Launch Staging Containers:**

   ```bash
   cd /opt/proofflow/infra
   docker-compose -f docker-compose.staging.yml up -d --build
   ```

4. **Verify Container Health:**

   ```bash
   docker ps
   # Both proofflow-api-staging and proofflow-web-staging should display (healthy)
   curl -i http://localhost:8000/health
   curl -i http://localhost:3000/health
   ```

5. **Configure Reverse Proxy (Caddy with Automatic TLS):**
   Install Caddy on the host (`apt install -y caddy`) and configure `/etc/caddy/Caddyfile`:

   ```caddy
   api-staging.proofflow.yourdomain.com {
       reverse_proxy 127.0.0.1:8000
   }

   staging.proofflow.yourdomain.com {
       reverse_proxy 127.0.0.1:3000
   }
   ```

   Reload Caddy:

   ```bash
   systemctl reload caddy
   ```

---

### Workflow 2: Render PaaS with Persistent Disk (Option A)

1. **Deploy API as a Web Service:**
   - In Render Dashboard, click **New -> Web Service**.
   - Connect repository, choose Docker environment, Dockerfile path: `apps/api/Dockerfile`, Docker build context: `.`.
   - Under **Instance Type**, select **Starter** ($7/mo).
   - Under **Disks**, click **Add Disk**:
     - Name: `proofflow-evidence`
     - Mount Path: `/app/storage/evidence`
     - Size: `3 GB` ($1/mo)
   - Under **Health Check Path**, enter `/health`.
   - Set environment variables as defined in Section 4.

2. **Deploy Web as a Web Service:**
   - In Render Dashboard, click **New -> Web Service**.
   - Dockerfile path: `apps/web/Dockerfile`, Docker build context: `.`.
   - Under **Health Check Path**, enter `/health`.
   - Add build arguments:
     - `NEXT_PUBLIC_API_URL`: Your Render backend service URL
     - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: Your Clerk publishable key
   - Set environment variables as defined in Section 4.

---

## 7. Post-Deployment Verification Checklist

Once deployed to staging, perform the following end-to-end checks before declaring staging ready:

- [ ] **Liveness / Readiness:** `curl https://api-staging.../health` returns `200` with `"database": "connected"`.
- [ ] **Fail-Closed Auth Test:** `curl -X POST https://api-staging.../api/v1/cases` without Authorization header returns `401 Unauthorized`.
- [ ] **CORS Verification:** Preflight `OPTIONS https://api-staging.../api/v1/cases` with `Origin: https://staging...` returns `200 OK` with allowed credentials.
- [ ] **Clerk Login Flow:** Open frontend staging URL in browser, log in via Clerk, and observe case dashboard loads.
- [ ] **Evidence Persistence Test:**
  1. Upload a sample dispute PDF.
  2. Verify events are extracted and timeline renders.
  3. Restart the backend container (`docker-compose restart api`).
  4. Reload the case page and verify evidence and extracted events are still fully intact.
- [ ] **PDF Dossier Export:** Click "Generate Dossier" and "Download PDF". Verify the generated dispute dossier downloads cleanly.
