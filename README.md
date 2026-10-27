# HelpDesk API

Role-based IT helpdesk ticketing REST API with SLA tracking, SQL reports and a Streamlit dashboard.

[![CI](https://github.com/pasupunuri-pragnitha/HelpDesk-API/actions/workflows/ci.yml/badge.svg)](https://github.com/pasupunuri-pragnitha/HelpDesk-API/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![MySQL 8](https://img.shields.io/badge/mysql-8.0-4479A1.svg)
![Tests](https://img.shields.io/badge/tests-167%20collected-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Ticket Workflow](#ticket-workflow)
- [Database Schema](#database-schema)
- [AI Triage & Duplicate Detection](#ai-triage--duplicate-detection)
- [API Overview](#api-overview)
- [Quick Start](#quick-start)
- [Demo Data](#demo-data)
- [Testing & Quality](#testing--quality)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Project Structure](#project-structure)
- [Author](#author)

---

## Features

| Capability | Description |
| :--- | :--- |
| **Authentication & Roles** | JWT authentication with bcrypt hashing (72-byte limit validation). Three roles: `requester`, `agent`, and `admin`. |
| **Ticket Workflow** | Enforced state transitions (`open` -> `in_progress` <-> `waiting_on_requester`, `in_progress` -> `resolved` -> `closed`, with reopen). Invalid moves return 409. |
| **Business-Hours SLA** | SLA calculated strictly within configurable working hours (`WORK_TIMEZONE`, `WORK_DAY_START`, `WORK_DAY_END`, `WORK_DAYS`) and organization holidays. |
| **Pausable SLA Clock** | Moving to `waiting_on_requester` freezes the SLA clock (`sla_paused_at`); resuming to `in_progress` pushes `due_at` forward by exact elapsed business minutes. |
| **Holidays Management** | Admin CRUD API for organizational holiday calendars (`/api/v1/holidays`), preventing SLA calculations on non-working dates. |
| **AI Triage & Duplicates** | Advisory category/priority suggestions via similarity-weighted kNN voting; duplicate detection over active tickets using L2-normalized cosine embeddings. |
| **Comments & History** | Public comments and staff-only `is_internal` notes. Full status change audit history recorded on state changes. |
| **Search & Pagination** | Sanitized keyword search (`q`), multi-criteria filtering, multi-field sorting, and offset pagination. |
| **SQL Reports** | 9 raw SQL reports using aggregations, `LEFT JOIN`, Common Table Expressions (CTEs), and `RANK()` window functions. |

---

## Architecture

The system uses a layered architecture separating transport, business logic, persistence, and presentation.

```mermaid
flowchart TD
    Client["Streamlit Dashboard (Port 8501)"] -->|"HTTP / REST (JWT Auth)"| Routes["FastAPI Routes (/api/v1)"]
    Routes --> Services["Service Layer (Business Logic & Workflows)"]
    Services --> AI["AI Layer (HashingVectorizer / SBERT Embeddings)"]
    Services --> Models["SQLAlchemy 2.x Models"]
    Models --> DB[("MySQL 8 Database")]
    Alembic["Alembic Migrations"] -.->|"Schema DDL"| DB
    CI["GitHub Actions CI"] -.->|"Automated Tests & Migration Check"| Routes
```

---

## Ticket Workflow

The ticket lifecycle follows an explicit state transition machine managed entirely in the service layer.

```mermaid
stateDiagram-v2
    [*] --> open : Ticket Created
    open --> in_progress : Agent Assigned / Work Started
    in_progress --> waiting_on_requester : Pauses SLA Clock (Waiting for Requester)
    waiting_on_requester --> in_progress : Resumes SLA Clock (Pushes due_at by Business Minutes)
    in_progress --> resolved : Resolution Provided
    resolved --> closed : Requester / Admin Closes Ticket
    resolved --> in_progress : Reopened by Staff
    closed --> [*]
```

Any invalid or out-of-order state transition is rejected with an HTTP 409 Conflict status. Tickets in `waiting_on_requester` freeze the SLA clock and are never flagged as overdue while paused.

---

## Database Schema

```mermaid
erDiagram
    users {
        int id PK
        string email UK
        string full_name
        string hashed_password
        enum role
        boolean is_active
        datetime created_at
    }

    tickets {
        int id PK
        string title
        text description
        enum status
        enum priority
        enum category
        int requester_id FK
        int assignee_id FK
        datetime due_at
        datetime sla_paused_at
        datetime created_at
        datetime updated_at
    }

    holidays {
        int id PK
        date holiday_date UK
        string name
        datetime created_at
    }

    ticket_comments {
        int id PK
        int ticket_id FK
        int author_id FK
        text body
        boolean is_internal
        datetime created_at
    }

    ticket_status_history {
        int id PK
        int ticket_id FK
        int changed_by_id FK
        enum from_status
        enum to_status
        datetime created_at
    }

    ticket_embeddings {
        int ticket_id PK,FK
        string model_name
        int dim
        blob vector
        datetime updated_at
    }

    users ||--o{ tickets : "creates (requester)"
    users ||--o{ tickets : "assigned (assignee)"
    users ||--o{ ticket_comments : "authors"
    users ||--o{ ticket_status_history : "changes"
    tickets ||--o{ ticket_comments : "has"
    tickets ||--o{ ticket_status_history : "audits"
    tickets ||--o| ticket_embeddings : "embeds"
```

---

## AI Triage & Duplicate Detection

The AI layer provides automated, advisory category and priority suggestions as well as proactive duplicate ticket detection.

### How It Works

1. **Text Representation (Embeddings)**: When a ticket is created or updated, its `title` and `description` are embedded into a fixed-dimensional unit-norm (L2-normalized) numerical vector (`app/ai/embedder.py`).
2. **Fast Cosine Similarity**: Because all vectors are normalized to unit length ($\|u\|_2 = \|v\|_2 = 1$), the cosine similarity between the query text and historical tickets reduces to an ultra-fast dot product:
   $$\text{cosine\_similarity}(u, v) = u \cdot v$$
3. **Category & Priority Suggestion**:
   - Compares the issue against historically **resolved** and **closed** tickets with similarity $\ge$ `AI_MIN_SIMILARITY` (default: `0.12`).
   - Retrieves the top $k$ neighbours (`AI_KNN_K`, default: `5`).
   - Performs a similarity-weighted vote ($w_i = s_i$):
     $$\text{Vote}(c) = \sum_{i \in \text{top-k},\, \text{label}_i = c} s_i$$
   - Confidence is computed as the proportion of winning category weight over total neighbour weight:
     $$\text{Confidence} = \frac{\text{Vote}(c^*)}{\sum_{i \in \text{top-k}} s_i}$$
   - Returns `null` suggestions with `confidence = 0.0` if no neighbours exceed the minimum threshold.
4. **Duplicate Detection**:
   - Scans active, unresolved tickets (`open`, `in_progress`, `waiting_on_requester`) for high similarity ($\ge$ `AI_DUPLICATE_THRESHOLD`, default: `0.80`).
5. **Strict Privacy Isolation**:
   - Requesters **only** receive evidence items and possible duplicates from their own tickets (`requester_id == current_user.id`). They never see foreign ticket IDs, titles, or descriptions.
   - Category and priority votes aggregate across the entire knowledge base without leaking individual ticket details.
6. **Advisory by Design**: Suggestions never automatically mutate a ticket. They guide agents and requesters while keeping humans firmly in control. Failure of the AI layer never prevents ticket creation or updates.

### Endpoints

- `POST /api/v1/triage/suggest`: Computes advisory category/priority suggestions and duplicate candidates from `title` and `description` for any authenticated user.
- `GET /api/v1/tickets/{id}/similar`: Returns similar tickets to an existing ticket, excluding itself. Restricted to `agent` and `admin` roles (returns 403 for requesters, 404 if ticket does not exist; optional `?limit=` between 1 and 20).

### Configuration Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `AI_EMBEDDER` | `"hashing"` | Active embedding backend (`hashing` / `hashing-v2` or `sbert`). |
| `AI_DUPLICATE_THRESHOLD` | `0.80` | Minimum cosine similarity to flag an unresolved ticket as a duplicate. |
| `AI_MIN_SIMILARITY` | `0.12` | Minimum cosine similarity required to participate in kNN voting. |
| `AI_KNN_K` | `5` | Number of nearest neighbours used for category/priority voting. |
| `AI_MAX_CANDIDATES` | `5000` | Maximum candidate pool loaded for similarity ranking. |

### Optional Dense Embedder (Sentence-Transformers)

The default `hashing` backend requires zero downloads or external model weights. To enable dense semantic embeddings using `all-MiniLM-L6-v2`:

```powershell
pip install -r requirements-ai.txt
```

Then set `AI_EMBEDDER=sbert` in `.env`.

### Benchmark & Evaluation

Evaluation is performed via `app/scripts/eval_triage.py` on a synthetic evaluation dataset (`data/triage_eval.csv`, 120 synthetic tickets balanced across all 6 categories):

```powershell
# Standard evaluation on held-out test split (24 tickets)
python -m app.scripts.eval_triage

# Run 5-fold cross-validation sweep on train split only, then evaluate test split
python -m app.scripts.eval_triage --tune
```

> [!NOTE]
> The evaluation dataset `data/triage_eval.csv` is strictly synthetic benchmark demo data. The test split is never used for parameter tuning.

#### 5-Fold Cross-Validation on Train Split Only ($N=96$)
Threshold tuning for `AI_MIN_SIMILARITY` was conducted via 5-fold stratified cross-validation exclusively on the 96 training tickets:

| `min_sim` | Coverage | Acc (when made) | Overall Acc (inc No Sugg) | Priority Overall |
| :--- | :--- | :--- | :--- | :--- |
| `0.05` | 100.0% | 59.5% | 59.5% | 33.6% |
| `0.08` | 100.0% | 59.5% | 59.5% | 33.6% |
| `0.10` | 100.0% | 59.5% | 59.5% | 33.6% |
| **`0.12`** *(chosen)* | **100.0%** | **60.6%** | **60.6%** | **33.6%** |
| `0.15` | 94.7% | 56.3% | 53.3% | 37.7% |
| `0.18` | 75.0% | 54.6% | 40.6% | 32.5% |
| `0.20` | 52.0% | 64.0% | 33.3% | 23.1% |
| `0.25` | 16.5% | 64.3% | 10.3% | 6.2% |
| `0.30` | 4.1% | 0.0% | 0.0% | 0.0% |

**Why `0.12` was selected**: On the training folds, `0.12` achieves 100% suggestion coverage while maximizing overall category accuracy at 60.6%. Higher thresholds like `0.20` drop coverage sharply (down to 52.0% coverage and 33.3% overall accuracy), rejecting viable suggestions as "no suggestion".

#### Final Evaluation on Test Split ($N=24$)

| Metric | Before (`hashing`, sim=0.20) | After (`hashing-v2`, sim=0.12) | Random Chance | Majority Class |
| :--- | :--- | :--- | :--- | :--- |
| **Suggestion Coverage** | 16.67% (4/24) | **100.00%** (24/24) | — | — |
| **Category Accuracy (Overall)** | 16.67% (4/24) | **58.33%** (14/24) | 16.67% (1 of 6) | 16.67% (20/120) |
| **Category Acc (When Made)** | 16.67% (4/24) | **58.33%** (14/24) | 16.67% | 16.67% |
| **Priority Accuracy (Overall)** | 8.33% (2/24) | **37.50%** (9/24) | 25.00% (1 of 4) | 38.33% |
| **Priority Acc (When Made)** | 8.33% (2/24) | **37.50%** (9/24) | 25.00% | 38.33% |

**Per-Category Accuracy Breakdown (`hashing-v2`)**:
- `access`: **100.00%** (4/4)
- `hardware`: **75.00%** (3/4)
- `network`: **75.00%** (3/4)
- `email`: **50.00%** (2/4)
- `other`: **25.00%** (1/4)
- `software`: **25.00%** (1/4)

#### Interview Talking Point: How did you evaluate AI triage and what were the trade-offs?
> *"Our initial baseline had an unacceptable 83% 'no suggestion' rate because an uncalibrated threshold (0.20) sat above the median cosine similarity of word-only sparse vectors, and common English stop words diluted signal. We redesigned the embedder (`hashing-v2`) to combine word 1-2 grams with stop words removed and sublinear TF scaling ($1 + \log(\text{tf})$) alongside character 3-5 n-grams for morphological resilience ('disconnects' vs 'disconnecting'), normalized to 4096 dimensions.*
>
> *We tuned `AI_MIN_SIMILARITY` honestly using 5-fold cross-validation strictly on the training set (never touching the test set), identifying 0.12 as the optimal operating point balancing 100% coverage and 60.6% training accuracy. On the held-out test split, overall category accuracy jumped from 16.67% (chance level) to 58.33% (14/24), ~3.5x higher than random chance (16.67%). Priority accuracy stands at 37.50%—priority is inherently more subjective across ticket creators.*
>
> *The remaining gap to higher accuracy stems from dataset scale (only 16 training tickets per class) and semantic overlap across IT domains (e.g., 'backup drive' spanning Hardware vs Network). Because the embedder interface is fully decoupled, production deployments needing >80% accuracy can seamlessly drop in sentence-transformers (`sbert`) with zero database schema or service modifications."*

---

## API Overview

All routes are prefixed with `/api/v1`. Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Register a new user account (defaults to requester role) | Public |
| `POST` | `/api/v1/auth/login` | Authenticate with email and password, returning JWT | Public |
| `GET` | `/api/v1/users/me` | Retrieve profile of the currently authenticated user | Authenticated |
| `GET` | `/api/v1/users` | List registered users with pagination parameters | Admin |
| `PATCH` | `/api/v1/users/{id}/role` | Update role of a specific user | Admin |
| `POST` | `/api/v1/tickets` | Create a new support ticket (calculates business-hours SLA `due_at`) | Authenticated |
| `GET` | `/api/v1/tickets` | List tickets with filters (status, priority, category, assignee, overdue), search, and pagination | Authenticated |
| `GET` | `/api/v1/tickets/{id}` | Get ticket details (returns 404 if accessed by foreign requester) | Authenticated |
| `GET` | `/api/v1/tickets/{id}/similar` | Retrieve tickets similar to a specific ticket, excluding itself (optional `?limit=`) | Agent / Admin |
| `PATCH` | `/api/v1/tickets/{id}` | Update title, description, priority, or category | Owner (open) / Agent (category) / Admin |
| `PATCH` | `/api/v1/tickets/{id}/status` | Transition status (pauses SLA clock on `waiting_on_requester`; pushes `due_at` on resume) | Agent / Admin |
| `PATCH` | `/api/v1/tickets/{id}/assign` | Assign ticket to an agent (transitions open -> in_progress) | Agent / Admin |
| `POST` | `/api/v1/tickets/{id}/comments` | Add comment (staff can set `is_internal=true`) | Owner / Agent / Admin |
| `GET` | `/api/v1/tickets/{id}/comments` | List ticket comments (internal notes hidden from requesters) | Owner / Agent / Admin |
| `GET` | `/api/v1/tickets/{id}/history` | Retrieve full status transition history audit trail | Owner / Agent / Admin |
| `POST` | `/api/v1/triage/suggest` | Advisory category/priority suggestions and duplicate detection | Authenticated |
| `POST` | `/api/v1/holidays` | Register an organization holiday date (409 on duplicate date) | Admin |
| `GET` | `/api/v1/holidays` | List registered organization holidays, ordered by date (optional `?year=`) | Agent / Admin |
| `DELETE` | `/api/v1/holidays/{id}` | Remove an organization holiday by ID (404 if missing) | Admin |
| `GET` | `/api/v1/reports/tickets-by-status` | Aggregated ticket counts grouped by status and priority | Agent / Admin |
| `GET` | `/api/v1/reports/overdue` | List overdue tickets past SLA due date with requester and assignee (excludes paused) | Agent / Admin |
| `GET` | `/api/v1/reports/resolution-time` | Average resolution hours per agent calculated via CTE | Agent / Admin |
| `GET` | `/api/v1/reports/agent-ranking` | Agent performance ranking calculated via `RANK()` function | Agent / Admin |
| `GET` | `/api/v1/reports/daily-volume` | Daily creation volume over a configurable window (1–90 days) | Agent / Admin |
| `GET` | `/api/v1/reports/sla-breach-rate` | SLA breach rate and compliance counts per ticket priority (paused tickets not overdue) | Agent / Admin |
| `GET` | `/api/v1/reports/resolution-time-by-category` | Average resolution hours grouped by category and priority | Agent / Admin |
| `GET` | `/api/v1/reports/agent-workload` | Agent workload summary: open work, overdue tickets, and resolved counts | Agent / Admin |
| `GET` | `/api/v1/reports/tickets-by-category` | Ticket counts grouped by category, optionally broken down by status | Agent / Admin |
| `GET` | `/api/v1/health` | Health check endpoint confirming API and database connectivity | Public |


---

## Quick Start

Follow these steps to run the API and Streamlit dashboard locally on Windows PowerShell.

### 1. Clone the repository

```powershell
git clone https://github.com/pasupunuri-pragnitha/HelpDesk-API.git
cd HelpDesk-API
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pip install -r dashboard/requirements.txt
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Key configuration settings (with default values):

- `DATABASE_URL`: Connection string for MySQL 8 (`mysql+pymysql://helpdesk:helpdesk_password@localhost:3306/helpdesk_db`)
- `SECRET_KEY`: Secret string for HMAC-SHA256 JWT encoding
- `WORK_TIMEZONE`: Timezone for working hours evaluation (default: `Asia/Kolkata`)
- `WORK_DAY_START`: Working day operational start time (default: `09:00`)
- `WORK_DAY_END`: Working day operational end time (default: `18:00`)
- `WORK_DAYS`: Operational days as JSON list of integers 0=Mon..6=Sun (default: `[0, 1, 2, 3, 4]`)

### 5. Start MySQL database container

```powershell
docker compose up -d db
```

### 6. Run database migrations

```powershell
alembic upgrade head
```

### 7. Create an initial administrator account

```powershell
python -m app.scripts.create_admin --email admin@example.com --password <your-password> --name "System Admin"
```

### 8. Run the FastAPI backend

```powershell
uvicorn app.main:app --reload --port 8000
```

### 9. Run the Streamlit dashboard

In a separate PowerShell terminal:

```powershell
streamlit run dashboard/app.py
```

For dashboard details, see [dashboard/README.md](dashboard/README.md).

---

## Demo Data

To populate the database with realistic sample tickets across all 6 categories, 4 priorities, workflow statuses (including `waiting_on_requester`), public/internal comments, and overdue SLA scenarios, run the demo seed script:

```powershell
# Using the safety confirmation flag
python -m app.scripts.seed_demo --yes

# Or via environment variable
$env:ALLOW_DEMO_SEED="1"
python -m app.scripts.seed_demo
```

### Demo Accounts

| Role | Email | Password | Full Name |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@example.com` | `AdminPassword123!` | System Admin |
| **Agent** | `agent@example.com` | `AgentPassword123!` | Asha Agent |
| **Requester** | `requester@example.com` | `RequesterPassword123!` | Ravi Requester |

> [!WARNING]
> **Production Security Warning**: These demo accounts use well-known, public passwords. The seed script is strictly intended for local development, demonstration, and automated test environments. **Never run this script on or enable these accounts in a production deployment.**

---

## Testing & Quality

| Metric | Value |
| :--- | :--- |
| **Pytest Tests** | 167 collected (163 passed, 4 skipped without optional dependencies/MySQL URL) |
| **Code Coverage** | 95% (`app`) |
| **Database Migrations** | 8 Alembic migrations |
| **User Roles** | 3 (`requester`, `agent`, `admin`) |
| **SQL Reports** | 9 raw SQL reports |

Run the test suite locally with coverage reporting:
```powershell
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

GitHub Actions CI runs the full test suite with coverage enforcement and executes MySQL 8 migration checks (`upgrade -> downgrade -> upgrade`) on every push and pull request.

---

## Design Decisions

- **404 Instead of 403 for Foreign Tickets**: Requesters attempting to view another user's ticket receive a 404 Not Found rather than 403 Forbidden to prevent ticket ID enumeration.
- **Requester Identity Bound to JWT**: The `requester_id` is always extracted from the authenticated user token, preventing users from creating tickets on behalf of others.
- **Service-Layer State Machine**: Status transitions are defined centrally in `app/services/tickets.py` rather than within routes, guaranteeing uniform business rule enforcement.
- **Business-Hours SLA & Pausable Clock**: SLA deadlines (`due_at`) are calculated strictly during operational business hours, skipping off-hours, weekends, and database-registered holidays. Transitioning a ticket to `waiting_on_requester` pauses the SLA clock by setting `sla_paused_at`, removing it from overdue queries. Returning to `in_progress` computes exact elapsed business minutes and shifts `due_at` forward proportionally.
- **Advisory AI Triage & Privacy**: Category and priority suggestions use similarity-weighted k-Nearest Neighbours over historically resolved tickets. Recommendations never auto-mutate tickets; requesters only see their own tickets in evidence and duplicate candidate lists.
- **Bcrypt 72-Byte Limit Validation**: Pydantic validators explicitly check the UTF-8 byte length (maximum 72 bytes) before passing passwords to bcrypt, avoiding silent password truncation.
- **Dual-Engine Test Strategy**: Local unit tests run against fast in-memory SQLite (`sqlite:///:memory:`) for sub-second execution, while CI executes against MySQL 8 to validate SQL window functions and migrations (which caught a real MySQL-only downgrade bug in migration 0002).
- **Correlation Request-ID Logging**: Middleware extracts or generates an `X-Request-ID` stored in `contextvars`, including it in all log entries across the request lifecycle without logging sensitive tokens or passwords.

---

## Known Limitations

- **Lexical vs. Semantic AI Triage**: The default `hashing-v2` backend uses sublinear-scaled word n-grams (with stop words removed) and character 3-5 n-grams (dim=4096). On our benchmark dataset, category accuracy reaches 58.33% with 100% suggestion coverage (at threshold 0.12). For enterprise semantic understanding with deep context, install `requirements-ai.txt` to enable the `sbert` (`all-MiniLM-L6-v2`) embedder. Accuracy scales naturally as the volume of resolved tickets grows.
- **Offset Pagination**: Pagination uses standard SQL `LIMIT` / `OFFSET`, which is straightforward for moderate datasets but less performant on massive tables than keyset pagination.
- **User Roster Access**: Only admins can list users; agents must input target agent IDs manually when assigning tickets.
- **No Email Notifications**: Ticket lifecycle events and comments are tracked in database history rather than sending outbound email alerts.

---

## Roadmap

- [ ] Keyset/cursor-based pagination for high-volume ticket archives
- [ ] Email notifications via SMTP/SendGrid on status and comment events
- [ ] File and image attachment uploads for tickets and comments

---

## Project Structure

```text
.
├── alembic/              # Database migration configuration and version scripts
├── app/                  # FastAPI backend application core, models, schemas, and routes
│   ├── ai/               # AI embedder protocols, HashingVectorizer, and SBERT backends
│   ├── api/              # API route definitions and dependency injection
│   ├── core/             # Configuration, logging middleware, security, and SLA definitions
│   ├── db/               # Database engine, session management, and Base declarative model
│   ├── models/           # SQLAlchemy entity models and enums
│   ├── schemas/          # Pydantic models for validation and response serialization
│   ├── scripts/          # Administrative CLI utilities (admin, demo seed, reindex, eval)
│   └── services/         # Business logic layer (tickets workflow, reports, auth, triage)
├── dashboard/            # Streamlit web portal client and analytics views
├── data/                 # Benchmark evaluation dataset (synthetic helpdesk tickets)
├── docs/                 # Documentation assets
├── tests/                # Automated pytest test suites and client mocks
├── docker-compose.yml    # Multi-container orchestration for MySQL 8 and backend
├── Dockerfile            # Container build specification for FastAPI app
├── pytest.ini            # Pytest configuration and coverage settings
├── requirements.txt      # Production runtime dependencies
├── requirements-ai.txt   # Optional semantic embedding dependencies (sentence-transformers)
└── requirements-dev.txt  # Development and testing dependencies
```

---

## Author

**Pasupunuri Pragnitha**  
- GitHub: [pasupunuri-pragnitha](https://github.com/pasupunuri-pragnitha)  
- LinkedIn: [pragnitha-pasupunuri](https://www.linkedin.com/in/pragnitha-pasupunuri)
