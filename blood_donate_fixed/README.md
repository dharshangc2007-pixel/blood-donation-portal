# ❤️ LifeFlow – Blood Donation Portal

A complete, full-stack blood donation management system with a premium dark-themed frontend and a Python-powered REST API backend. Donors can self-register through a multi-step form, and administrators manage all data through a secure dashboard.

---

## 📋 Table of Contents

1. [Problem Statement](#problem-statement)
2. [Introduction](#introduction)
3. [Objectives](#objectives)
4. [Technologies Used](#technologies-used)
5. [System Architecture](#system-architecture)
6. [Database Design](#database-design)
7. [API Documentation](#api-documentation)
8. [Installation & Setup](#installation--setup)
9. [Running the Application](#running-the-application)
10. [Admin Account Setup](#admin-account-setup)
11. [Testing Guide](#testing-guide)
12. [Deployment Notes](#deployment-notes)
13. [Security Features](#security-features)
14. [Project Structure](#project-structure)

---

## Problem Statement

Blood shortages are a critical global health challenge. Traditional donor management relies on paper records, phone calls, and manual processes that are slow, error-prone, and inaccessible. LifeFlow solves this by digitising the entire donor registration and management lifecycle.

---

## Introduction

**LifeFlow** is a Blood Donation Camp Management Portal built for organisations running blood donation drives. It allows:
- **Donors** to register online with full medical information
- **Admins** to manage donor records, blood requests, and contact messages through a real-time dashboard
- **Visitors** to learn about eligibility, upcoming camps, and how to participate

---

## Objectives

- Provide a seamless online donor registration experience
- Maintain a searchable, filterable database of all registered donors
- Enable admins to approve/reject/manage donor records
- Track blood requests and contact messages
- Ensure data security and prevent unauthorised access
- Generate donor statistics by blood group, type, and status

---

## Technologies Used

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, Vanilla CSS, Vanilla JavaScript |
| Backend | Python 3 (stdlib only — `http.server`, `sqlite3`, `json`) |
| Database | SQLite (file: `lifeflow.db`) |
| Authentication | HMAC-SHA256 token-based auth |
| Styling | Custom CSS with glassmorphism & animations |
| Fonts | Google Fonts — Inter, Poppins |

> **No Node.js, npm, or external Python packages required.**

---

## System Architecture

```
Browser (HTML/CSS/JS)
        │
        │  HTTP REST API (fetch)
        ▼
Python http.server (server.py)  ←→  SQLite (lifeflow.db)
        │
        └── Static file serving (all .html, .css, .js files)
```

### Flow
1. User opens `index.html` → static file served by Python
2. Registration form submits `POST /api/register`
3. Backend validates, saves to SQLite, returns donor ID
4. Admin logs in via `POST /api/admin/login` → receives token
5. Dashboard calls `GET /api/admin/donors?token=...` → returns real data
6. All admin mutations (edit, delete, status) are token-protected

---

## Database Design

### `donors`
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | Auto-increment donor ID |
| first_name, last_name | TEXT | Full name |
| email | TEXT | Unique email |
| phone | TEXT | Phone number |
| dob | TEXT | Date of birth (YYYY-MM-DD) |
| age | INTEGER | Computed from DOB |
| gender | TEXT | male/female/other/prefer_not |
| gov_id | TEXT | Aadhaar / Govt ID (not exposed via API) |
| occupation | TEXT | Optional |
| address | TEXT | Full address |
| emergency_name | TEXT | Emergency contact name |
| emergency_phone | TEXT | Emergency contact phone |
| blood_group | TEXT | A+/A-/B+/B-/O+/O-/AB+/AB-/unknown |
| weight | REAL | Body weight in kg |
| donation_type | TEXT | whole_blood/platelets/plasma/double_red |
| previous_donation | TEXT | yes/no |
| last_donation_date | TEXT | Optional |
| donation_count | INTEGER | Number of past donations |
| conditions | TEXT | Comma-separated medical conditions |
| medications | TEXT | Current medications |
| allergies | TEXT | Known allergies |
| hemoglobin | REAL | Hemoglobin level (optional) |
| availability | TEXT | available/unavailable/on_leave |
| status | TEXT | pending/approved/rejected |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |

### `admins`
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | |
| username | TEXT UNIQUE | Login username |
| email | TEXT | Admin email |
| password_hash | TEXT | salt:hmac-sha256 |
| role | TEXT | admin/superadmin |
| created_at | TEXT | |

### `blood_requests`
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PK | |
| patient_name | TEXT | Patient requiring blood |
| requester_name | TEXT | Person making the request |
| contact_phone | TEXT | Contact number |
| blood_group | TEXT | Required blood group |
| units_required | INTEGER | Number of units |
| hospital_name | TEXT | Hospital name |
| hospital_city | TEXT | Location |
| urgency | TEXT | normal/urgent/critical |
| status | TEXT | pending/fulfilled/cancelled |

### `contacts`
Contact messages from the contact page.

### `admin_logs`
Audit log of admin actions (edit, delete, status changes).

---

## API Documentation

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Dashboard statistics (public) |
| POST | `/api/register` | Register a new donor |
| POST | `/api/contact` | Submit a contact message |
| POST | `/api/requests` | Submit a blood request |

### Admin Endpoints (require `Authorization: Bearer <token>` header)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/login` | Admin login (returns token) |
| POST | `/api/admin/logout` | Invalidate token |
| GET | `/api/admin/stats` | Full statistics |
| GET | `/api/admin/donors` | Paginated donor list with filters |
| GET | `/api/admin/donors/:id` | Single donor details |
| PUT | `/api/admin/donors/:id` | Edit donor fields |
| PATCH | `/api/admin/donors/:id/status` | Update status (pending/approved/rejected) |
| PATCH | `/api/admin/donors/:id/availability` | Update availability |
| DELETE | `/api/admin/donors/:id` | Delete donor |
| GET | `/api/admin/donors/export?token=` | Export all donors as CSV |
| GET | `/api/admin/contacts` | Paginated contact messages |
| PATCH | `/api/admin/contacts/:id/status` | Update message status |
| DELETE | `/api/admin/contacts/:id` | Delete message |
| GET | `/api/admin/requests` | Paginated blood requests |
| PATCH | `/api/admin/requests/:id/status` | Update request status |
| DELETE | `/api/admin/requests/:id` | Delete request |

### Query Parameters for `/api/admin/donors`
- `search` — search by name/email/phone
- `blood` — filter by blood group (e.g. `A+`)
- `status` — filter by pending/approved/rejected
- `avail` — filter by available/unavailable/on_leave
- `sort` — sort column (id, first_name, blood_group, age, created_at, status)
- `order` — asc or desc
- `page` — page number (default 1)
- `limit` — records per page (max 100, default 25)

---

## Installation & Setup

### Prerequisites
- Python 3.8 or later (check: `python --version`)
- A modern web browser

### Steps

```bash
# 1. Clone or download the project
git clone https://github.com/dharshangc2007-pixel/blood-donation-portal.git
cd blood-donation-portal

# 2. (Optional) Set custom admin credentials via environment variables
#    Windows PowerShell:
$env:LIFEFLOW_ADMIN_USER = "your_username"
$env:LIFEFLOW_ADMIN_PASS = "Your$ecureP@ss123"

# 3. Start the server
python server.py
```

The server will:
- Create `lifeflow.db` automatically on first run
- Seed the default admin account
- Print the admin credentials to the console

---

## Running the Application

After starting the server:

| URL | Purpose |
|-----|---------|
| `http://localhost:5000/` | Main donor portal (homepage) |
| `http://localhost:5000/register.html` | Donor registration |
| `http://localhost:5000/admin-login.html` | Admin login |
| `http://localhost:5000/admin.html` | Admin dashboard |
| `http://localhost:5000/api/stats` | Live API stats (JSON) |

---

## Admin Account Setup

### Default Credentials
```
Username: admin
Password: Admin@123
```

### Changing the Password (Recommended)

**Method 1 – Environment variables (recommended):**
```powershell
# Windows PowerShell
$env:LIFEFLOW_ADMIN_USER = "yourusername"
$env:LIFEFLOW_ADMIN_PASS = "YourNewSecurePassword!"
python server.py
```

**Method 2 – Edit `.env.example`, rename to `.env` and load before starting.**

> ⚠️ Never use the default password in production.

---

## Testing Guide

### 1. Register a Donor
1. Open `http://localhost:5000/register.html`
2. Fill all required fields
3. Accept all consent checkboxes
4. Click **Submit Registration**
5. ✅ A success overlay should appear with your Donor ID

### 2. Verify in Admin Dashboard
1. Open `http://localhost:5000/admin-login.html`
2. Login with `admin` / `Admin@123`
3. Go to **Donors** section
4. ✅ Your new registration should appear in the table

### 3. Test Search & Filters
- Search by name, email, or phone
- Filter by blood group or status
- Sort columns by clicking headers

### 4. Test Edit/Delete
- Click **View** to see full donor details
- Click **Edit** to modify fields
- Click **Del** → confirm to delete

### 5. Test Duplicate Registration
- Try registering with the same email twice
- ✅ Should return "An account with this email already exists."

### 6. Test Unauthorised Access
- Try accessing `http://localhost:5000/api/admin/donors` without a token
- ✅ Should return 401 Unauthorized

### 7. Test CSV Export
- In the Donors section, click **⬇ Export CSV**
- ✅ Should download a `.csv` file with all donor records

---

## Deployment Notes

For production deployment:

1. **Use a production WSGI server** (e.g. Gunicorn + Nginx) instead of `http.server`
2. **Set strong admin credentials** via environment variables
3. **Use HTTPS** — configure SSL via Nginx or a reverse proxy
4. **Restrict CORS** — change `Access-Control-Allow-Origin: *` to your domain
5. **Backup the database** — schedule regular copies of `lifeflow.db`
6. **Consider migrating to PostgreSQL** for high-traffic production use

---

## Security Features

| Feature | Implementation |
|---------|---------------|
| Password hashing | HMAC-SHA256 with random salt |
| Authentication | Token-based (64-char hex, 8-hour TTL) |
| Rate limiting | Max 10 login attempts per 60 seconds per IP |
| Input validation | Server-side validation of all required fields |
| Duplicate prevention | Unique email constraint on registration |
| Age validation | Enforces 18–65 donor age requirement |
| File upload security | Extension allowlist, 5MB size limit |
| Gov ID protection | `gov_id` never returned by any API |
| SQL injection | Parameterised queries throughout |
| Directory traversal | Path resolution + relative check for static files |

---

## Project Structure

```
blood-donation-portal/
├── index.html           # Homepage
├── about.html           # About page
├── eligibility.html     # Eligibility checker
├── register.html        # Donor registration form
├── schedule.html        # Camp schedule
├── contact.html         # Contact form
├── admin-login.html     # Admin login page   ← NEW
├── admin.html           # Admin dashboard    ← NEW
├── styles.css           # Shared CSS
├── shared.js            # Shared JavaScript
├── server.py            # Python backend     ← ENHANCED
├── lifeflow.db          # SQLite database (auto-created)
├── .env.example         # Environment variable template ← NEW
├── README.md            # This file          ← NEW
└── uploads/             # Uploaded photo IDs (gitignored)
```

---

## Credits

Built with ❤️ for LifeFlow Medical Foundation, Tamil Nadu, India.  
© 2025 LifeFlow. All rights reserved.
