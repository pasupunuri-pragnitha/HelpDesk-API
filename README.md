# HelpDesk API

[![CI](https://github.com/<USERNAME>/<REPO>/actions/workflows/ci.yml/badge.svg)](https://github.com/<USERNAME>/<REPO>/actions/workflows/ci.yml)

A high-performance IT HelpDesk Ticketing REST API built with FastAPI, SQLAlchemy 2.x, MySQL 8, and Alembic.

## Features
- **Authentication & RBAC**: Secure JWT-based authentication (bcrypt password hashing with UTF-8 byte validation) with role-based access control (`requester`, `agent`, `admin`).
- **Ticket Workflow**: Strict status transitions (`open` -> `in_progress` -> `resolved` -> `closed`, plus reopen).
- **Audit History & Comments**: Real-time status history logging and internal/public comment visibility filtering.
- **SLA & Overdue Tracking**: Automatic SLA due date computation per priority and dynamic overdue evaluation.
- **Search, Filtering & Pagination**: Case-insensitive keyword search (`q`) with wildcard escaping, multi-field filters, stable sorting, and offset pagination.
- **Structured Logging & Request Tracing**: Standard-library request ID tracking via `contextvars` and middleware.
- **Database Migrations**: Version-controlled schema migrations with Alembic for MySQL.

## Local Development & Testing

### Running Tests with Coverage
```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```
