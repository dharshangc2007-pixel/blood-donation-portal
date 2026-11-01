"""
LifeFlow Blood Donation Portal – Backend Server
================================================
Python 3 stdlib-only HTTP server (no Node.js required).
Serves static files + REST API on http://localhost:5000

Admin default: admin / Admin@123  (change via environment variables)
  LIFEFLOW_ADMIN_USER  = your_username
  LIFEFLOW_ADMIN_PASS  = your_secure_password
"""

import http.server
import json
import sqlite3
import os
import mimetypes
import urllib.parse
import re
import hashlib
import hmac
import secrets
import datetime
import csv
import io
from pathlib import Path
from collections import defaultdict

# ─── Configuration ───────────────────────────────────────────────────────────
def _load_dotenv():
    """Load KEY=VALUE pairs from a .env file next to server.py (if present)."""
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()

PORT        = int(os.environ.get('PORT', '5000'))
HOST        = os.environ.get('HOST', 'localhost')
DB_FILE     = Path(__file__).parent / os.environ.get('DB_FILE', 'lifeflow.db')
STATIC_DIR  = Path(__file__).parent
UPLOADS_DIR = Path(__file__).parent / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

# Admin credentials – override with environment variables (never hardcode in production)
ADMIN_USERNAME = os.environ.get('LIFEFLOW_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('LIFEFLOW_ADMIN_PASS', 'Admin@123')

HMAC_SECRET = os.environ.get('LIFEFLOW_SECRET_KEY', 'lifeflow-secret-key').encode('utf-8')

# Token store: { token: expiry_datetime }
ADMIN_TOKENS: dict = {}
TOKEN_TTL_HOURS = 8

# Rate-limit store: { ip: [timestamp, ...] }
_rate_store: dict = defaultdict(list)
RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX    = 10   # max attempts per window per IP

# ─── Token helpers ────────────────────────────────────────────────────────────

def _make_token() -> str:
    return secrets.token_hex(32)

def _valid_token(token: str) -> bool:
    if not token:
        return False
    exp = ADMIN_TOKENS.get(token)
    if not exp:
        return False
    if datetime.datetime.now() > exp:
        ADMIN_TOKENS.pop(token, None)
        return False
    return True

def _hash_password(password: str) -> str:
    """SHA-256 + HMAC for password hashing (stdlib-only, no bcrypt)."""
    salt = secrets.token_hex(16)
    key  = (salt + password).encode('utf-8')
    h    = hmac.new(HMAC_SECRET, key, hashlib.sha256).hexdigest()
    return f"{salt}:{h}"

def _check_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(':', 1)
        key     = (salt + password).encode('utf-8')
        expected = hmac.new(HMAC_SECRET, key, hashlib.sha256).hexdigest()
        return hmac.compare_digest(h, expected)
    except Exception:
        return False

# ─── Rate limiting ───────────────────────────────────────────────────────────

def _rate_limited(ip: str) -> bool:
    now  = datetime.datetime.now().timestamp()
    hits = [t for t in _rate_store[ip] if now - t < RATE_LIMIT_WINDOW]
    _rate_store[ip] = hits
    if len(hits) >= RATE_LIMIT_MAX:
        return True
    _rate_store[ip].append(now)
    return False

# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    # ── Donors table ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS donors (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name        TEXT    NOT NULL,
            last_name         TEXT    NOT NULL,
            email             TEXT    NOT NULL,
            phone             TEXT    NOT NULL,
            dob               TEXT    NOT NULL,
            age               INTEGER,
            gender            TEXT    NOT NULL,
            gov_id            TEXT    NOT NULL,
            occupation        TEXT,
            address           TEXT    NOT NULL,
            emergency_name    TEXT    NOT NULL,
            emergency_phone   TEXT    NOT NULL,
            blood_group       TEXT    NOT NULL,
            weight            REAL    NOT NULL,
            donation_type     TEXT    NOT NULL,
            previous_donation TEXT    NOT NULL,
            last_donation_date TEXT,
            donation_count    INTEGER DEFAULT 0,
            conditions        TEXT,
            medications       TEXT,
            allergies         TEXT,
            hemoglobin        REAL,
            referral_source   TEXT,
            referrer_name     TEXT,
            additional_notes  TEXT,
            newsletter        INTEGER DEFAULT 0,
            form_version      TEXT,
            availability      TEXT    DEFAULT 'available',
            status            TEXT    DEFAULT 'pending',
            created_at        TEXT    NOT NULL,
            updated_at        TEXT
        )
    ''')
    _try_alter(cur, "ALTER TABLE donors ADD COLUMN availability TEXT DEFAULT 'available'")
    _try_alter(cur, "ALTER TABLE donors ADD COLUMN updated_at TEXT")
    _try_alter(cur, "ALTER TABLE donors ADD COLUMN photo_id_file TEXT")

    # ── Contacts table ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            email        TEXT    NOT NULL,
            phone        TEXT,
            subject      TEXT    NOT NULL,
            inquiry_type TEXT    NOT NULL,
            message      TEXT    NOT NULL,
            urgency      INTEGER DEFAULT 1,
            newsletter   INTEGER DEFAULT 0,
            status       TEXT    DEFAULT 'unread',
            created_at   TEXT    NOT NULL
        )
    ''')

    # ── Admins table ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL UNIQUE,
            email        TEXT,
            password_hash TEXT   NOT NULL,
            role         TEXT    DEFAULT 'admin',
            created_at   TEXT    NOT NULL
        )
    ''')
    # Seed default admin
    existing = cur.execute("SELECT id FROM admins WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO admins (username, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (ADMIN_USERNAME, 'admin@lifeflow.org', _hash_password(ADMIN_PASSWORD), 'superadmin',
             datetime.datetime.now().isoformat())
        )

    # ── Blood requests table ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS blood_requests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name   TEXT    NOT NULL,
            requester_name TEXT    NOT NULL,
            contact_phone  TEXT    NOT NULL,
            contact_email  TEXT,
            blood_group    TEXT    NOT NULL,
            units_required INTEGER NOT NULL,
            hospital_name  TEXT    NOT NULL,
            hospital_city  TEXT    NOT NULL,
            urgency        TEXT    NOT NULL DEFAULT 'normal',
            reason         TEXT,
            status         TEXT    NOT NULL DEFAULT 'pending',
            notes          TEXT,
            created_at     TEXT    NOT NULL,
            updated_at     TEXT
        )
    ''')

    # ── Admin activity log ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admin_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user TEXT    NOT NULL,
            action     TEXT    NOT NULL,
            target     TEXT,
            details    TEXT,
            created_at TEXT    NOT NULL
        )
    ''')

    con.commit()
    con.close()
    print('[DB] Database ready at ' + str(DB_FILE))

def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

def _try_alter(cur, sql):
    try:
        cur.execute(sql)
    except Exception:
        pass

# ─── CORS ────────────────────────────────────────────────────────────────────

CORS_HEADERS = {
    'Access-Control-Allow-Origin':  '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization',
}

PUBLIC_EXTENSIONS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp', '.gif'}

# ─── Request Handler ─────────────────────────────────────────────────────────

class LifeFlowHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        print('  [' + ts + '] ' + (fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path.rstrip('/')
        qs     = urllib.parse.parse_qs(parsed.query)

        # Public
        if path == '/api/stats':
            self._json(self._get_stats()); return
        if path == '/api/donors':
            self._json(self._get_donors_public()); return

        # Admin-protected
        if path == '/api/admin/donors':
            if not self._auth(qs): return
            self._json(self._admin_get_donors(qs)); return

        if re.match(r'^/api/admin/donors/\d+$', path):
            if not self._auth(qs): return
            donor_id = path.split('/')[-1]
            self._json(self._admin_get_donor(donor_id)); return

        if path == '/api/admin/stats':
            if not self._auth(qs): return
            self._json(self._get_stats()); return

        if path == '/api/admin/contacts':
            if not self._auth(qs): return
            self._json(self._admin_get_contacts(qs)); return

        if path == '/api/admin/requests':
            if not self._auth(qs): return
            self._json(self._admin_get_requests(qs)); return

        if path == '/api/admin/donors/export':
            if not self._auth(qs): return
            self._export_donors_csv(qs); return

        m = re.match(r'^/api/admin/donors/(\d+)/photo$', path)
        if m:
            if not self._auth(qs): return
            self._serve_donor_photo(m.group(1)); return

        # Serve static files
        self._serve_static(parsed.path)

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        routes = {
            '/api/register':              self._handle_register,
            '/api/contact':               self._handle_contact,
            '/api/requests':              self._handle_blood_request,
            '/api/admin/login':           self._handle_admin_login,
            '/api/admin/logout':          self._handle_admin_logout,
        }
        if path in routes:
            routes[path]()
        else:
            self._error(404, 'Endpoint not found')

    # ── PUT ──────────────────────────────────────────────────────────────────
    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        if re.match(r'^/api/admin/donors/\d+$', path):
            donor_id = path.split('/')[-1]
            self._handle_donor_edit(donor_id); return

        self._error(404, 'Endpoint not found')

    # ── PATCH ────────────────────────────────────────────────────────────────
    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        m = re.match(r'^/api/admin/donors/(\d+)/status$', path)
        if m:
            self._handle_donor_status(m.group(1)); return

        m = re.match(r'^/api/admin/donors/(\d+)/availability$', path)
        if m:
            self._handle_donor_availability(m.group(1)); return

        m = re.match(r'^/api/admin/requests/(\d+)/status$', path)
        if m:
            self._handle_request_status(m.group(1)); return

        m = re.match(r'^/api/admin/contacts/(\d+)/status$', path)
        if m:
            self._handle_contact_status(m.group(1)); return

        self._error(404, 'Endpoint not found')

    # ── DELETE ───────────────────────────────────────────────────────────────
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        m = re.match(r'^/api/admin/donors/(\d+)$', path)
        if m:
            self._handle_donor_delete(m.group(1)); return

        m = re.match(r'^/api/admin/contacts/(\d+)$', path)
        if m:
            self._handle_contact_delete(m.group(1)); return

        m = re.match(r'^/api/admin/requests/(\d+)$', path)
        if m:
            self._handle_request_delete(m.group(1)); return

        self._error(404, 'Endpoint not found')

    # ── Auth helper ───────────────────────────────────────────────────────────
    def _auth(self, qs=None) -> bool:
        token = None
        if qs:
            token = qs.get('token', [None])[0]
        if not token:
            auth = self.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        if not token or not _valid_token(token):
            self._error(401, 'Unauthorized. Please log in first.')
            return False
        return True

    def _get_token_from_body(self, data: dict) -> str:
        return data.get('token', '')

    def _get_admin_user(self, qs=None) -> str:
        """Extract admin username from token for logging."""
        token = None
        if qs:
            token = qs.get('token', [None])[0]
        if not token:
            auth = self.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        return ADMIN_TOKENS.get('_user_' + (token or ''), 'admin')

    def _log_action(self, admin: str, action: str, target: str = '', details: str = ''):
        try:
            con = sqlite3.connect(DB_FILE)
            con.execute(
                "INSERT INTO admin_logs (admin_user, action, target, details, created_at) VALUES (?,?,?,?,?)",
                (admin, action, target, details, datetime.datetime.now().isoformat())
            )
            con.commit(); con.close()
        except Exception:
            pass

    # ── Body reader ───────────────────────────────────────────────────────────
    def _read_json_body(self) -> dict:
        length = int(self.headers.get('Content-Length', 0))
        if not length:
            return {}
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except Exception:
            return {}

    # ── Admin Login / Logout ──────────────────────────────────────────────────
    def _handle_admin_login(self):
        ip = self.client_address[0]
        if _rate_limited(ip):
            self._json({'success': False, 'message': 'Too many attempts. Try again in 60 seconds.'}, 429)
            return
        try:
            data     = self._read_json_body()
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()

            con = sqlite3.connect(DB_FILE)
            row = con.execute(
                "SELECT password_hash, role FROM admins WHERE username = ?", (username,)
            ).fetchone()
            con.close()

            valid = False
            if row:
                valid = _check_password(password, row[0])
            # Also allow env-variable direct check (legacy fallback)
            if not valid and username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                valid = True

            if valid:
                token = _make_token()
                ADMIN_TOKENS[token] = datetime.datetime.now() + datetime.timedelta(hours=TOKEN_TTL_HOURS)
                ADMIN_TOKENS['_user_' + token] = username
                print(f'  [ADMIN] Login: {username} from {ip}')
                self._json({'success': True, 'token': token,
                            'username': username,
                            'message': 'Login successful', 'expiresInHours': TOKEN_TTL_HOURS})
            else:
                self._json({'success': False, 'message': 'Invalid username or password.'}, 401)
        except Exception as e:
            self._error(500, str(e))

    def _handle_admin_logout(self):
        data  = self._read_json_body()
        token = data.get('token', '') or (self.headers.get('Authorization', '')[7:])
        ADMIN_TOKENS.pop(token, None)
        ADMIN_TOKENS.pop('_user_' + token, None)
        self._json({'success': True, 'message': 'Logged out successfully.'})

    # ── Donor Registration (public) ───────────────────────────────────────────
    def _handle_register(self):
        try:
            ct = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in ct:
                length = int(self.headers.get('Content-Length', 0))
                body   = self.rfile.read(length)
                data   = self._parse_multipart(body, ct)
            elif 'application/json' in ct:
                data = self._read_json_body()
            else:
                length = int(self.headers.get('Content-Length', 0))
                raw    = self.rfile.read(length).decode('utf-8')
                qs     = urllib.parse.parse_qs(raw, keep_blank_values=True)
                data   = {k: (v[0] if len(v) == 1 else ','.join(v)) for k, v in qs.items()}

            # Required field validation
            required = ['firstName', 'lastName', 'email', 'phone', 'dob', 'gender',
                        'govId', 'address', 'emergencyName', 'emergencyPhone',
                        'bloodGroup', 'weight', 'donationType', 'previousDonation']
            missing = [f for f in required if not str(data.get(f, '')).strip()]
            if missing:
                self._json({'success': False, 'message': 'Missing required fields: ' + ', '.join(missing)}, 400)
                return

            # Email validation
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', data.get('email', '')):
                self._json({'success': False, 'message': 'Invalid email address.'}, 400); return

            # Phone validation
            phone_clean = re.sub(r'[\s\-\+]', '', data.get('phone', ''))
            if not re.match(r'^\d{10,15}$', phone_clean):
                self._json({'success': False, 'message': 'Invalid phone number (10-15 digits).'}, 400); return

            # Age from DOB
            try:
                dob   = datetime.datetime.strptime(data['dob'], '%Y-%m-%d').date()
                today = datetime.date.today()
                age   = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age < 18 or age > 65:
                    self._json({'success': False, 'message': 'Donor age must be between 18 and 65.'}, 400); return
            except Exception:
                age = None

            # Weight validation
            try:
                weight = float(data.get('weight', 0) or 0)
                if weight < 50:
                    self._json({'success': False, 'message': 'Minimum weight for donation is 50 kg.'}, 400); return
            except Exception:
                weight = 0

            # Duplicate check (email)
            con = sqlite3.connect(DB_FILE)
            dup = con.execute("SELECT id FROM donors WHERE email = ?", (data['email'].strip().lower(),)).fetchone()
            if dup:
                con.close()
                self._json({'success': False, 'message': 'An account with this email already exists.'}, 409); return

            cur = con.cursor()
            now = datetime.datetime.now().isoformat()
            cur.execute('''INSERT INTO donors (
                first_name, last_name, email, phone, dob, age, gender,
                gov_id, occupation, address, emergency_name, emergency_phone,
                blood_group, weight, donation_type, previous_donation,
                last_donation_date, donation_count, conditions, medications,
                allergies, hemoglobin, referral_source, referrer_name,
                additional_notes, newsletter, form_version, availability, status, created_at, updated_at, photo_id_file
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                data.get('firstName','').strip(), data.get('lastName','').strip(),
                data.get('email','').strip().lower(), data.get('phone','').strip(),
                data.get('dob',''), age, data.get('gender',''),
                data.get('govId','').strip(),  data.get('occupation',''),
                data.get('address','').strip(), data.get('emergencyName','').strip(),
                data.get('emergencyPhone','').strip(), data.get('bloodGroup',''),
                weight, data.get('donationType',''), data.get('previousDonation',''),
                data.get('lastDonationDate','') or None,
                int(data.get('donationCount', 0) or 0),
                data.get('conditions',''), data.get('medications',''), data.get('allergies',''),
                float(data.get('hemoglobin', 0)) if data.get('hemoglobin') else None,
                data.get('referralSource',''), data.get('referrerName',''),
                data.get('additionalNotes',''),
                1 if data.get('newsletter') in ('on','true','1') else 0,
                data.get('formVersion','2025-v3'),
                'available', 'pending', now, now,
                Path(data['photoId']).name if data.get('photoId') else None
            ))
            donor_id = cur.lastrowid
            con.commit(); con.close()

            name = (data.get('firstName','') + ' ' + data.get('lastName','')).strip()
            print(f'  [DB] Donor #{donor_id}: {name} ({data.get("bloodGroup","")})')
            self._json({
                'success':    True,
                'message':    f'Registration successful! Welcome, {name}! Your Donor ID is #{donor_id}.',
                'donorId':    donor_id,
                'name':       name,
                'bloodGroup': data.get('bloodGroup','')
            })
        except Exception as e:
            print(f'  [ERROR] Register: {e}')
            self._json({'success': False, 'message': 'Server error. Please try again.'}, 500)

    # ── Contact form (public) ─────────────────────────────────────────────────
    def _handle_contact(self):
        try:
            ct = self.headers.get('Content-Type', '')
            if 'application/json' in ct:
                data = self._read_json_body()
            else:
                length = int(self.headers.get('Content-Length', 0))
                raw    = self.rfile.read(length).decode('utf-8')
                qs     = urllib.parse.parse_qs(raw, keep_blank_values=True)
                data   = {k: (v[0] if len(v) == 1 else ','.join(v)) for k, v in qs.items()}

            required = ['cName', 'cEmail', 'cSubject', 'cMessage']
            missing  = [f for f in required if not data.get(f, '').strip()]
            if missing:
                self._json({'success': False, 'message': 'Missing: ' + ', '.join(missing)}, 400); return

            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute('''INSERT INTO contacts
                (name, email, phone, subject, inquiry_type, message, urgency, newsletter, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (
                data.get('cName','').strip(), data.get('cEmail','').strip(),
                data.get('cPhone','').strip(), data.get('cSubject',''),
                data.get('inquiryType','general'), data.get('cMessage','').strip(),
                int(data.get('cUrgency',1) or 1),
                1 if data.get('cNewsletter') in ('on','true','1') else 0,
                'unread', datetime.datetime.now().isoformat()
            ))
            cid = cur.lastrowid
            con.commit(); con.close()
            self._json({'success': True, 'message': 'Message received! We will respond within 2 hours.', 'contactId': cid})
        except Exception as e:
            self._json({'success': False, 'message': 'Server error.'}, 500)

    # ── Blood Request (public) ────────────────────────────────────────────────
    def _handle_blood_request(self):
        try:
            data = self._read_json_body()
            required = ['patientName', 'requesterName', 'contactPhone', 'bloodGroup', 'unitsRequired', 'hospitalName', 'hospitalCity']
            missing  = [f for f in required if not str(data.get(f,'')).strip()]
            if missing:
                self._json({'success': False, 'message': 'Missing: ' + ', '.join(missing)}, 400); return

            now = datetime.datetime.now().isoformat()
            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute('''INSERT INTO blood_requests
                (patient_name, requester_name, contact_phone, contact_email, blood_group, units_required,
                 hospital_name, hospital_city, urgency, reason, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                data.get('patientName','').strip(),
                data.get('requesterName','').strip(),
                data.get('contactPhone','').strip(),
                data.get('contactEmail','').strip(),
                data.get('bloodGroup',''),
                int(data.get('unitsRequired', 1)),
                data.get('hospitalName','').strip(),
                data.get('hospitalCity','').strip(),
                data.get('urgency','normal'),
                data.get('reason',''),
                'pending', now, now
            ))
            rid = cur.lastrowid
            con.commit(); con.close()
            self._json({'success': True, 'message': 'Blood request submitted.', 'requestId': rid})
        except Exception as e:
            self._json({'success': False, 'message': str(e)}, 500)

    # ── Admin – Get donors ────────────────────────────────────────────────────
    def _admin_get_donors(self, qs):
        search   = qs.get('search',  [''])[0]
        blood    = qs.get('blood',   [''])[0]
        status_f = qs.get('status',  [''])[0]
        avail_f  = qs.get('avail',   [''])[0]
        sort     = qs.get('sort',    ['id'])[0]
        order    = 'DESC' if qs.get('order', ['desc'])[0].lower() == 'desc' else 'ASC'
        page     = max(1, _int(qs.get('page',  ['1'])[0], 1))
        limit    = min(100, max(1, _int(qs.get('limit', ['25'])[0], 25)))
        offset   = (page - 1) * limit

        allowed = {'id','first_name','last_name','blood_group','age','created_at','donation_type','status','availability'}
        if sort not in allowed:
            sort = 'id'

        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        wheres, params = [], []
        if search:
            wheres.append("(first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR blood_group LIKE ?)")
            s = '%' + search + '%'
            params += [s, s, s, s, s]
        if blood:
            wheres.append("blood_group = ?"); params.append(blood)
        if status_f:
            wheres.append("status = ?"); params.append(status_f)
        if avail_f:
            wheres.append("availability = ?"); params.append(avail_f)

        where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
        total = cur.execute(f'SELECT COUNT(*) FROM donors {where_sql}', params).fetchone()[0]
        rows  = cur.execute(
            f'SELECT * FROM donors {where_sql} ORDER BY {sort} {order} LIMIT ? OFFSET ?',
            params + [limit, offset]
        ).fetchall()
        con.close()
        return {'success': True, 'total': total, 'page': page, 'limit': limit,
                'donors': [self._safe_donor(dict(r)) for r in rows]}

    def _admin_get_donor(self, donor_id):
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM donors WHERE id = ?', (donor_id,)).fetchone()
        con.close()
        if not row:
            return {'success': False, 'message': 'Donor not found'}
        return {'success': True, 'donor': self._safe_donor(dict(row))}

    def _safe_donor(self, d: dict) -> dict:
        """Remove sensitive fields before returning to frontend."""
        d.pop('gov_id', None)
        return d

    # ── Admin – Edit donor (PUT) ──────────────────────────────────────────────
    def _handle_donor_edit(self, donor_id):
        try:
            token = (self.headers.get('Authorization','')[7:])
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return

            data    = self._read_json_body()
            allowed = ['first_name','last_name','email','phone','blood_group','gender',
                       'occupation','address','emergency_name','emergency_phone',
                       'availability','status','additional_notes']
            if 'status' in data and data['status'] not in ('pending','approved','rejected'):
                self._error(400, 'Invalid status'); return
            if 'availability' in data and data['availability'] not in ('available','unavailable','on_leave'):
                self._error(400, 'Invalid availability'); return
            sets, vals = [], []
            for field in allowed:
                if field in data:
                    sets.append(f'{field} = ?')
                    vals.append(data[field])
            if not sets:
                self._json({'success': False, 'message': 'No fields to update.'}); return

            sets.append('updated_at = ?')
            vals.append(datetime.datetime.now().isoformat())
            vals.append(donor_id)

            con = sqlite3.connect(DB_FILE)
            con.execute(f"UPDATE donors SET {', '.join(sets)} WHERE id = ?", vals)
            con.commit(); con.close()

            admin = ADMIN_TOKENS.get('_user_' + token, 'admin')
            self._log_action(admin, 'EDIT_DONOR', f'donor#{donor_id}', str(list(data.keys())))
            self._json({'success': True, 'message': f'Donor #{donor_id} updated.'})
        except Exception as e:
            self._error(500, str(e))

    # ── Admin – Donor status (PATCH) ──────────────────────────────────────────
    def _handle_donor_status(self, donor_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            data   = self._read_json_body()
            status = data.get('status','')
            if status not in ('pending','approved','rejected'):
                self._error(400,'Invalid status'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("UPDATE donors SET status = ?, updated_at = ? WHERE id = ?",
                        (status, datetime.datetime.now().isoformat(), donor_id))
            con.commit(); con.close()
            admin = ADMIN_TOKENS.get('_user_' + token, 'admin')
            self._log_action(admin, 'STATUS_DONOR', f'donor#{donor_id}', status)
            self._json({'success': True, 'message': f'Status set to {status}.'})
        except Exception as e:
            self._error(500, str(e))

    # ── Admin – Donor availability ────────────────────────────────────────────
    def _handle_donor_availability(self, donor_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            data  = self._read_json_body()
            avail = data.get('availability','')
            if avail not in ('available','unavailable','on_leave'):
                self._error(400,'Invalid availability'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("UPDATE donors SET availability = ?, updated_at = ? WHERE id = ?",
                        (avail, datetime.datetime.now().isoformat(), donor_id))
            con.commit(); con.close()
            self._json({'success': True, 'message': f'Availability set to {avail}.'})
        except Exception as e:
            self._error(500, str(e))

    # ── Admin – Delete donor ──────────────────────────────────────────────────
    def _handle_donor_delete(self, donor_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("DELETE FROM donors WHERE id = ?", (donor_id,))
            con.commit(); con.close()
            admin = ADMIN_TOKENS.get('_user_' + token, 'admin')
            self._log_action(admin, 'DELETE_DONOR', f'donor#{donor_id}')
            print(f'  [ADMIN] Deleted donor #{donor_id}')
            self._json({'success': True, 'message': f'Donor #{donor_id} deleted.'})
        except Exception as e:
            self._error(500, str(e))

    # ── Admin – Contacts ──────────────────────────────────────────────────────
    def _admin_get_contacts(self, qs):
        search   = qs.get('search',  [''])[0]
        status_f = qs.get('status',  [''])[0]
        page     = max(1, _int(qs.get('page', ['1'])[0], 1))
        limit    = min(100, max(1, _int(qs.get('limit', ['25'])[0], 25)))
        offset   = (page - 1) * limit
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        wheres, params = [], []
        if search:
            wheres.append("(name LIKE ? OR email LIKE ? OR subject LIKE ?)")
            s = '%' + search + '%'
            params += [s, s, s]
        if status_f:
            wheres.append("status = ?"); params.append(status_f)
        where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
        total = cur.execute(f'SELECT COUNT(*) FROM contacts {where_sql}', params).fetchone()[0]
        rows  = cur.execute(
            f'SELECT * FROM contacts {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?',
            params + [limit, offset]
        ).fetchall()
        con.close()
        return {'success': True, 'total': total, 'page': page, 'limit': limit,
                'contacts': [dict(r) for r in rows]}

    def _handle_contact_status(self, contact_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            data   = self._read_json_body()
            status = data.get('status','')
            if status not in ('unread','read','resolved'):
                self._error(400,'Invalid status'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("UPDATE contacts SET status = ? WHERE id = ?", (status, contact_id))
            con.commit(); con.close()
            self._json({'success': True, 'message': 'Contact status updated.'})
        except Exception as e:
            self._error(500, str(e))

    def _handle_contact_delete(self, contact_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            con.commit(); con.close()
            self._json({'success': True, 'message': f'Contact #{contact_id} deleted.'})
        except Exception as e:
            self._error(500, str(e))

    # ── Admin – Blood Requests ────────────────────────────────────────────────
    def _admin_get_requests(self, qs):
        search   = qs.get('search',  [''])[0]
        blood    = qs.get('blood',   [''])[0]
        status_f = qs.get('status',  [''])[0]
        urgency  = qs.get('urgency', [''])[0]
        page     = max(1, _int(qs.get('page', ['1'])[0], 1))
        limit    = min(100, max(1, _int(qs.get('limit', ['25'])[0], 25)))
        offset   = (page - 1) * limit
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        wheres, params = [], []
        if search:
            wheres.append("(patient_name LIKE ? OR requester_name LIKE ? OR hospital_name LIKE ?)")
            s = '%' + search + '%'
            params += [s, s, s]
        if blood:
            wheres.append("blood_group = ?"); params.append(blood)
        if status_f:
            wheres.append("status = ?"); params.append(status_f)
        if urgency:
            wheres.append("urgency = ?"); params.append(urgency)
        where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
        total = cur.execute(f'SELECT COUNT(*) FROM blood_requests {where_sql}', params).fetchone()[0]
        rows  = cur.execute(
            f'SELECT * FROM blood_requests {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?',
            params + [limit, offset]
        ).fetchall()
        con.close()
        return {'success': True, 'total': total, 'page': page, 'limit': limit,
                'requests': [dict(r) for r in rows]}

    def _handle_request_status(self, req_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            data   = self._read_json_body()
            status = data.get('status','')
            if status not in ('pending','fulfilled','cancelled'):
                self._error(400,'Invalid status'); return
            now = datetime.datetime.now().isoformat()
            con = sqlite3.connect(DB_FILE)
            con.execute("UPDATE blood_requests SET status = ?, updated_at = ? WHERE id = ?", (status, now, req_id))
            con.commit(); con.close()
            self._json({'success': True, 'message': f'Request status updated to {status}.'})
        except Exception as e:
            self._error(500, str(e))

    def _handle_request_delete(self, req_id):
        try:
            token = self.headers.get('Authorization','')[7:]
            if not _valid_token(token):
                self._error(401,'Unauthorized'); return
            con = sqlite3.connect(DB_FILE)
            con.execute("DELETE FROM blood_requests WHERE id = ?", (req_id,))
            con.commit(); con.close()
            self._json({'success': True, 'message': f'Request #{req_id} deleted.'})
        except Exception as e:
            self._error(500, str(e))

    # ── CSV Export ────────────────────────────────────────────────────────────
    def _export_donors_csv(self, qs):
        token = qs.get('token', [None])[0]
        if not token or not _valid_token(token):
            self._error(401, 'Unauthorized'); return
        try:
            con = sqlite3.connect(DB_FILE)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id, first_name, last_name, email, phone, dob, age, gender, "
                "blood_group, address, availability, status, created_at "
                "FROM donors ORDER BY id"
            ).fetchall()
            con.close()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID','First Name','Last Name','Email','Phone','DOB','Age','Gender',
                             'Blood Group','Address','Availability','Status','Registered At'])
            for r in rows:
                writer.writerow([r['id'], r['first_name'], r['last_name'], r['email'], r['phone'],
                                 r['dob'], r['age'], r['gender'], r['blood_group'], r['address'],
                                 r['availability'], r['status'], r['created_at']])

            csv_bytes = output.getvalue().encode('utf-8-sig')
            filename  = f'donors_{datetime.date.today().isoformat()}.csv'
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', len(csv_bytes))
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(csv_bytes)
        except Exception as e:
            self._error(500, str(e))

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _get_stats(self):
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        total     = cur.execute('SELECT COUNT(*) FROM donors').fetchone()[0]
        approved  = cur.execute("SELECT COUNT(*) FROM donors WHERE status='approved'").fetchone()[0]
        pending   = cur.execute("SELECT COUNT(*) FROM donors WHERE status='pending'").fetchone()[0]
        rejected  = cur.execute("SELECT COUNT(*) FROM donors WHERE status='rejected'").fetchone()[0]
        available = cur.execute("SELECT COUNT(*) FROM donors WHERE availability='available'").fetchone()[0]
        msgs      = cur.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]
        unread    = cur.execute("SELECT COUNT(*) FROM contacts WHERE status='unread'").fetchone()[0]
        req_total = cur.execute('SELECT COUNT(*) FROM blood_requests').fetchone()[0]
        req_pend  = cur.execute("SELECT COUNT(*) FROM blood_requests WHERE status='pending'").fetchone()[0]
        byblood   = cur.execute('SELECT blood_group, COUNT(*) FROM donors GROUP BY blood_group ORDER BY 2 DESC').fetchall()
        recent    = cur.execute(
            "SELECT first_name||' '||last_name, blood_group, created_at, status FROM donors ORDER BY id DESC LIMIT 10"
        ).fetchall()
        bytype    = cur.execute('SELECT donation_type, COUNT(*) FROM donors GROUP BY donation_type').fetchall()
        con.close()
        return {
            'success':        True,
            'totalDonors':    total,
            'approvedDonors': approved,
            'pendingDonors':  pending,
            'rejectedDonors': rejected,
            'availableDonors':available,
            'totalMessages':  msgs,
            'unreadMessages': unread,
            'totalRequests':  req_total,
            'pendingRequests':req_pend,
            'byBloodGroup':   [{'bloodGroup': r[0], 'count': r[1]} for r in byblood],
            'byDonationType': [{'type': r[0], 'count': r[1]} for r in bytype],
            'recentDonors':   [{'name': r[0], 'bloodGroup': r[1], 'registeredAt': r[2], 'status': r[3]} for r in recent],
        }

    def _get_donors_public(self):
        """Limited public endpoint – no sensitive info."""
        con = sqlite3.connect(DB_FILE)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute('SELECT id, first_name, last_name, blood_group, status, created_at FROM donors ORDER BY id DESC LIMIT 50')
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return {'success': True, 'count': len(rows), 'donors': rows}

    # ── Multipart parser ─────────────────────────────────────────────────────
    def _parse_multipart(self, body: bytes, content_type: str) -> dict:
        m = re.search(r'boundary=([^\s;]+)', content_type)
        if not m:
            return {}
        boundary  = m.group(1).strip('"')
        delimiter = ('--' + boundary).encode()
        data      = {}
        parts     = body.split(delimiter)
        for part in parts[1:]:
            if part in (b'--\r\n', b'--', b'\r\n', b''):
                continue
            if part.startswith(b'--'):
                continue
            sep = part.find(b'\r\n\r\n')
            if sep == -1:
                continue
            header_block = part[:sep].decode('utf-8', errors='replace')
            value_bytes  = part[sep+4:]
            if value_bytes.endswith(b'\r\n'):
                value_bytes = value_bytes[:-2]
            cd = re.search(r'Content-Disposition:[^\r\n]*?;\s*name="([^"]+)"', header_block, re.IGNORECASE)
            if not cd:
                continue
            field_name = cd.group(1)
            filename_m = re.search(r'filename="([^"]*)"', header_block, re.IGNORECASE)
            if filename_m and filename_m.group(1):
                fname_orig = filename_m.group(1)
                ext   = Path(fname_orig).suffix.lower()
                allowed_ext = {'.jpg','.jpeg','.png','.pdf'}
                if ext not in allowed_ext:
                    continue
                if len(value_bytes) > 5 * 1024 * 1024:
                    continue
                fname = field_name + '_' + datetime.datetime.now().strftime('%Y%m%d%H%M%S%f') + ext
                fpath = UPLOADS_DIR / fname
                fpath.write_bytes(value_bytes)
                data[field_name] = str(fpath)
            else:
                val = value_bytes.decode('utf-8', errors='replace')
                data[field_name] = (data.get(field_name, '') + ',' + val).lstrip(',') if field_name in data else val
        return data

    def _serve_donor_photo(self, donor_id):
        con = sqlite3.connect(DB_FILE)
        row = con.execute('SELECT photo_id_file FROM donors WHERE id = ?', (donor_id,)).fetchone()
        con.close()
        if not row or not row[0]:
            self._error(404, 'No photo ID on file'); return
        fpath = (UPLOADS_DIR / Path(row[0]).name).resolve()
        try:
            fpath.relative_to(UPLOADS_DIR.resolve())
        except ValueError:
            self._error(403, 'Forbidden'); return
        if not fpath.exists():
            self._error(404, 'File missing'); return
        mime = mimetypes.guess_type(str(fpath))[0] or 'application/octet-stream'
        content = fpath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', len(content))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    # ── Static file server ────────────────────────────────────────────────────
    def _serve_static(self, url_path: str):
        file_path = STATIC_DIR / (url_path.lstrip('/') or 'index.html')
        try:
            file_path = file_path.resolve()
            file_path.relative_to(STATIC_DIR.resolve())
        except (ValueError, RuntimeError):
            self._error(403, 'Forbidden'); return
        if file_path.is_dir():
            file_path = file_path / 'index.html'
        # Only public site assets are served; never the DB, source, docs, env files or uploads.
        rel = file_path.relative_to(STATIC_DIR.resolve())
        if (len(rel.parts) != 1 or rel.name.startswith('.')
                or rel.suffix.lower() not in PUBLIC_EXTENSIONS):
            self._error(404, 'File not found'); return
        if not file_path.exists():
            self._error(404, 'File not found'); return
        mime, _ = mimetypes.guess_type(str(file_path))
        mime   = mime or 'application/octet-stream'
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', len(content))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(content)

    # ── Response helpers ──────────────────────────────────────────────────────
    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, msg):
        self._json({'success': False, 'message': msg}, code)

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    server = http.server.HTTPServer((HOST, PORT), LifeFlowHandler)
    print()
    print('  ===========================================')
    print('   LIFEFLOW BLOOD DONATION PORTAL')
    print('  ===========================================')
    print('  Site:       http://' + HOST + ':' + str(PORT) + '/')
    print('  Admin:      http://' + HOST + ':' + str(PORT) + '/admin.html')
    print('  Login:      http://' + HOST + ':' + str(PORT) + '/admin-login.html')
    print('  API Stats:  http://' + HOST + ':' + str(PORT) + '/api/stats')
    print('  -------------------------------------------')
    print('  Admin User: ' + ADMIN_USERNAME)
    print('  Admin Pass: ' + ADMIN_PASSWORD)
    print('  ===========================================')
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[Server] Stopped.')
        server.server_close()
