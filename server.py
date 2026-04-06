import hashlib
import json
import math
import os
import secrets
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import parse, request
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "data" / "findit.db"


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class FindItStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        self.backend = "postgres" if self.database_url.startswith("postgres") else "sqlite"
        self._init_db()
        self._seed()

    def connect(self):
        if self.backend == "postgres":
            from psycopg import connect
            from psycopg.rows import dict_row
            return connect(self.database_url, row_factory=dict_row)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _prepare_query(self, query: str) -> str:
        if self.backend == "postgres":
            return query.replace("?", "%s")
        return query

    def _execute(self, conn, query, params=()):
        return conn.execute(self._prepare_query(query), params)

    def _executescript(self, conn, script: str):
        if self.backend == "sqlite":
            conn.executescript(script)
            return
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            if self.backend == "postgres":
                script = """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    faculty TEXT,
                    phone TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS listings (
                    id SERIAL PRIMARY KEY,
                    type TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    location TEXT NOT NULL,
                    description TEXT NOT NULL,
                    photo_url TEXT,
                    color TEXT,
                    listing_date TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_by INTEGER NOT NULL REFERENCES users (id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS claims (
                    id SERIAL PRIMARY KEY,
                    listing_id INTEGER NOT NULL REFERENCES listings (id) ON DELETE CASCADE,
                    claimant_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    proof_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );
                """
            else:
                script = """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    faculty TEXT,
                    phone TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    location TEXT NOT NULL,
                    description TEXT NOT NULL,
                    photo_url TEXT,
                    color TEXT,
                    listing_date TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                );

                CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    claimant_id INTEGER NOT NULL,
                    proof_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (listing_id) REFERENCES listings (id) ON DELETE CASCADE,
                    FOREIGN KEY (claimant_id) REFERENCES users (id) ON DELETE CASCADE
                );
                """
            self._executescript(conn, script)
            conn.commit()

    def _seed(self):
        with self.connect() as conn:
            count = self._execute(conn, "SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            if count:
                return

            users = [
                ("Admin User", "admin@knust.edu.gh", self.hash_password("admin123"), "admin", "Administration", "+233200000001"),
                ("Ama Serwaa", "ama@knust.edu.gh", self.hash_password("student123"), "student", "Engineering", "+233200000002"),
                ("Yaw Opoku", "yaw@knust.edu.gh", self.hash_password("student123"), "student", "Science", "+233200000003"),
            ]
            self._execute_many(
                conn,
                "INSERT INTO users (full_name, email, password_hash, role, faculty, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(n, e, p, r, f, ph, now_iso()) for n, e, p, r, f, ph in users],
            )

            listings = [
                ("lost", "Blue student ID card", "ID Card", "College of Engineering main block", "Blue holder with a faded black lanyard clip.", "", "Blue", "2026-04-03", "+233240000111", "open", 2),
                ("found", "Black HP laptop charger", "Electronics", "Central Library first floor", "Wrapped with black tape near the adapter head.", "", "Black", "2026-04-04", "+233240000222", "open", 3),
                ("found", "Brown leather wallet", "Wallet", "Republic Hall shuttle stop", "Contains a red meal card and folded receipts.", "", "Brown", "2026-04-02", "+233240000333", "claimed", 2),
                ("lost", "Silver key holder with 3 keys", "Keys", "Brunei hostel Block B", "Three keys on a silver ring with a football charm.", "", "Silver", "2026-04-01", "+233240000444", "resolved", 3),
            ]
            self._execute_many(
                conn,
                """
                INSERT INTO listings
                (type, item_name, category, location, description, photo_url, color, listing_date, contact_phone, status, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*row, now_iso(), now_iso()) for row in listings],
            )

            self._execute(
                conn,
                """
                INSERT INTO claims (listing_id, claimant_id, proof_text, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (3, 3, "The wallet contains a red meal card and a Tech Junction receipt.", "approved", now_iso()),
            )
            conn.commit()

    def _execute_many(self, conn, query, rows):
        prepared = self._prepare_query(query)
        if self.backend == "postgres":
            with conn.cursor() as cursor:
                cursor.executemany(prepared, rows)
        else:
            conn.executemany(prepared, rows)

    def _insert_and_get_id(self, conn, query, params):
        if self.backend == "postgres":
            cursor = self._execute(conn, query + " RETURNING id", params)
            return cursor.fetchone()["id"]
        cursor = self._execute(conn, query, params)
        return cursor.lastrowid

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def create_user(self, payload):
        with self.connect() as conn:
            existing = self._execute(conn, "SELECT id FROM users WHERE email = ?", (payload["email"],)).fetchone()
            if existing:
                raise ValueError("An account with that email already exists.")
            user_id = self._insert_and_get_id(
                conn,
                """
                INSERT INTO users (full_name, email, password_hash, role, faculty, phone, created_at)
                VALUES (?, ?, ?, 'student', ?, ?, ?)
                """,
                (
                    payload["full_name"],
                    payload["email"],
                    self.hash_password(payload["password"]),
                    payload.get("faculty", ""),
                    payload.get("phone", ""),
                    now_iso(),
                ),
            )
            conn.commit()
            return self.get_user(user_id)

    def authenticate(self, email, password):
        with self.connect() as conn:
            user = self._execute(conn, "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not user or user["password_hash"] != self.hash_password(password):
                return None
            return dict(user)

    def get_user(self, user_id):
        with self.connect() as conn:
            user = self._execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(user) if user else None

    def create_session(self, user_id):
        token = secrets.token_hex(24)
        with self.connect() as conn:
            self._execute(conn, "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, now_iso()))
            conn.commit()
        return token

    def get_session_user(self, token):
        if not token:
            return None
        with self.connect() as conn:
            row = self._execute(
                conn,
                """
                SELECT users.* FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token):
        with self.connect() as conn:
            self._execute(conn, "DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()

    def serialize_user(self, user):
        if not user:
            return None
        return {
            "id": user["id"],
            "fullName": user["full_name"],
            "email": user["email"],
            "role": user["role"],
            "faculty": user["faculty"],
            "phone": user["phone"],
        }

    def serialize_listing(self, row, include_claims=False):
        listing = {
            "id": row["id"],
            "type": row["type"],
            "itemName": row["item_name"],
            "category": row["category"],
            "location": row["location"],
            "description": row["description"],
            "photoUrl": row["photo_url"] or "",
            "color": row["color"] or "",
            "listingDate": row["listing_date"],
            "contactPhone": row["contact_phone"],
            "status": row["status"],
            "createdBy": row["created_by"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "claimsCount": row.get("claims_count", 0),
        }
        if include_claims:
            listing["claims"] = self.get_claims_for_listing(row["id"])
        return listing

    def listing_permissions(self, listing, user):
        is_owner = bool(user and listing["createdBy"] == user["id"])
        is_admin = bool(user and user["role"] == "admin")
        approved_claim = False
        if user and listing.get("claims"):
            approved_claim = any(claim["claimantId"] == user["id"] and claim["status"] == "approved" for claim in listing["claims"])
        return {
            "canEdit": is_owner or is_admin,
            "canDelete": is_owner or is_admin,
            "canClaim": bool(user and not is_owner and listing["status"] != "resolved"),
            "canModerate": is_admin,
            "canSeeContact": is_owner or is_admin or approved_claim,
        }

    def list_listings(self, filters):
        query = """
            SELECT listings.*, COUNT(claims.id) AS claims_count
            FROM listings
            LEFT JOIN claims ON claims.listing_id = listings.id
            WHERE 1=1
        """
        params = []
        if filters.get("type") and filters["type"] != "all":
            query += " AND listings.type = ?"
            params.append(filters["type"])
        if filters.get("status") and filters["status"] != "all":
            query += " AND listings.status = ?"
            params.append(filters["status"])
        if filters.get("category") and filters["category"] != "all":
            query += " AND listings.category = ?"
            params.append(filters["category"])
        if filters.get("search"):
            query += " AND (listings.item_name || ' ' || listings.location || ' ' || listings.description || ' ' || listings.category) LIKE ?"
            params.append(f"%{filters['search']}%")
        query += " GROUP BY listings.id ORDER BY listings.id DESC"
        with self.connect() as conn:
            rows = self._execute(conn, query, params).fetchall()
            return [self.serialize_listing(dict(row)) for row in rows]

    def get_listing(self, listing_id):
        with self.connect() as conn:
            row = self._execute(
                conn,
                """
                SELECT listings.*, COUNT(claims.id) AS claims_count
                FROM listings LEFT JOIN claims ON claims.listing_id = listings.id
                WHERE listings.id = ?
                GROUP BY listings.id
                """,
                (listing_id,),
            ).fetchone()
            if not row:
                return None
            return self.serialize_listing(dict(row), include_claims=True)

    def create_listing(self, user_id, payload):
        self.validate_listing_payload(payload)
        with self.connect() as conn:
            listing_id = self._insert_and_get_id(
                conn,
                """
                INSERT INTO listings
                (type, item_name, category, location, description, photo_url, color, listing_date, contact_phone, status, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    payload["type"],
                    payload["itemName"],
                    payload["category"],
                    payload["location"],
                    payload["description"],
                    payload.get("photoUrl", ""),
                    payload.get("color", ""),
                    payload["listingDate"],
                    payload["contactPhone"],
                    user_id,
                    now_iso(),
                    now_iso(),
                ),
            )
            conn.commit()
        return self.get_listing(listing_id)

    def update_listing(self, listing_id, payload):
        self.validate_listing_payload(payload)
        with self.connect() as conn:
            self._execute(
                conn,
                """
                UPDATE listings
                SET type = ?, item_name = ?, category = ?, location = ?, description = ?,
                    photo_url = ?, color = ?, listing_date = ?, contact_phone = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["type"],
                    payload["itemName"],
                    payload["category"],
                    payload["location"],
                    payload["description"],
                    payload.get("photoUrl", ""),
                    payload.get("color", ""),
                    payload["listingDate"],
                    payload["contactPhone"],
                    now_iso(),
                    listing_id,
                ),
            )
            conn.commit()
        return self.get_listing(listing_id)

    def create_claim(self, listing_id, user_id, proof_text):
        if not proof_text or len(proof_text.strip()) < 12:
            raise ValueError("Proof text should be at least 12 characters long.")
        with self.connect() as conn:
            exists = self._execute(
                conn,
                "SELECT id FROM claims WHERE listing_id = ? AND claimant_id = ? AND status IN ('pending', 'approved')",
                (listing_id, user_id),
            ).fetchone()
            if exists:
                raise ValueError("You already have an active claim on this listing.")
            self._execute(
                conn,
                "INSERT INTO claims (listing_id, claimant_id, proof_text, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (listing_id, user_id, proof_text, now_iso()),
            )
            self._execute(conn, "UPDATE listings SET status = 'claimed', updated_at = ? WHERE id = ? AND status = 'open'", (now_iso(), listing_id))
            conn.commit()
        return self.get_listing(listing_id)

    def get_claims_for_listing(self, listing_id):
        with self.connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT claims.*, users.full_name, users.email
                FROM claims
                JOIN users ON users.id = claims.claimant_id
                WHERE listing_id = ?
                ORDER BY claims.id DESC
                """,
                (listing_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "claimantId": row["claimant_id"],
                    "claimantName": row["full_name"],
                    "claimantEmail": row["email"],
                    "proofText": row["proof_text"],
                    "status": row["status"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    def list_claims_for_user(self, user_id):
        with self.connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT claims.*, listings.item_name, listings.category, listings.location, listings.status AS listing_status
                FROM claims
                JOIN listings ON listings.id = claims.listing_id
                WHERE claims.claimant_id = ?
                ORDER BY claims.id DESC
                """,
                (user_id,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "listingId": row["listing_id"],
                    "itemName": row["item_name"],
                    "category": row["category"],
                    "location": row["location"],
                    "listingStatus": row["listing_status"],
                    "status": row["status"],
                    "proofText": row["proof_text"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    def list_listings_for_user(self, user_id):
        with self.connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT listings.*, COUNT(claims.id) AS claims_count
                FROM listings LEFT JOIN claims ON claims.listing_id = listings.id
                WHERE listings.created_by = ?
                GROUP BY listings.id
                ORDER BY listings.id DESC
                """,
                (user_id,),
            ).fetchall()
            return [self.serialize_listing(dict(row)) for row in rows]

    def update_claim_status(self, claim_id, status):
        if status not in {"approved", "rejected", "pending"}:
            raise ValueError("Invalid claim status.")
        with self.connect() as conn:
            row = self._execute(conn, "SELECT listing_id FROM claims WHERE id = ?", (claim_id,)).fetchone()
            if not row:
                raise ValueError("Claim not found.")
            listing_id = row["listing_id"]
            self._execute(conn, "UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))
            if status == "approved":
                self._execute(conn, "UPDATE listings SET status = 'claimed', updated_at = ? WHERE id = ?", (now_iso(), listing_id))
            conn.commit()
        return self.get_listing(listing_id)

    def update_listing_status(self, listing_id, status):
        if status not in {"open", "claimed", "resolved"}:
            raise ValueError("Invalid listing status.")
        with self.connect() as conn:
            self._execute(conn, "UPDATE listings SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), listing_id))
            conn.commit()
        return self.get_listing(listing_id)

    def delete_listing(self, listing_id):
        with self.connect() as conn:
            self._execute(conn, "DELETE FROM listings WHERE id = ?", (listing_id,))
            conn.commit()

    def analytics(self):
        with self.connect() as conn:
            total = self._execute(conn, "SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
            resolved = self._execute(conn, "SELECT COUNT(*) AS count FROM listings WHERE status = 'resolved'").fetchone()["count"]
            open_count = self._execute(conn, "SELECT COUNT(*) AS count FROM listings WHERE status = 'open'").fetchone()["count"]
            claimed = self._execute(conn, "SELECT COUNT(*) AS count FROM listings WHERE status = 'claimed'").fetchone()["count"]
            by_category = self._execute(conn, "SELECT category AS label, COUNT(*) AS count FROM listings GROUP BY category ORDER BY count DESC").fetchall()
            by_location = self._execute(conn, "SELECT location AS label, COUNT(*) AS count FROM listings GROUP BY location ORDER BY count DESC LIMIT 6").fetchall()
            pending_claims = self._execute(conn, "SELECT COUNT(*) AS count FROM claims WHERE status = 'pending'").fetchone()["count"]
        recovery_rate = round((resolved / total) * 100, 1) if total else 0
        return {
            "totalReports": total,
            "resolvedReports": resolved,
            "openReports": open_count,
            "claimedReports": claimed,
            "pendingClaims": pending_claims,
            "recoveryRate": recovery_rate,
            "byCategory": [dict(row) for row in by_category],
            "byLocation": [dict(row) for row in by_location],
        }

    @staticmethod
    def validate_listing_payload(payload):
        required = ["type", "itemName", "category", "location", "description", "listingDate", "contactPhone"]
        for field in required:
            if not payload.get(field):
                raise ValueError(f"{field} is required.")
        if payload["type"] not in {"lost", "found"}:
            raise ValueError("Listing type must be lost or found.")
        if len(payload["itemName"].strip()) < 3:
            raise ValueError("Item name should be at least 3 characters long.")
        if len(payload["description"].strip()) < 10:
            raise ValueError("Description should be at least 10 characters long.")

    def match_listing(self, listing_id):
        target = self.get_listing(listing_id)
        if not target:
            return []
        candidates = [item for item in self.list_listings({}) if item["type"] != target["type"]]
        documents = [self._tokenize(item["itemName"] + " " + item["description"] + " " + item["location"] + " " + item["category"]) for item in candidates]
        target_tokens = self._tokenize(target["itemName"] + " " + target["description"] + " " + target["location"] + " " + target["category"])
        if not target_tokens:
            return []
        doc_freq = Counter()
        for tokens in documents + [target_tokens]:
            for token in set(tokens):
                doc_freq[token] += 1
        total_docs = len(documents) + 1
        target_vec = self._tfidf_vector(target_tokens, doc_freq, total_docs)
        matches = []
        for item, tokens in zip(candidates, documents):
            vector = self._tfidf_vector(tokens, doc_freq, total_docs)
            score = self._cosine_similarity(target_vec, vector)
            if target["category"] == item["category"]:
                score += 0.18
            if target["location"].split()[0].lower() in item["location"].lower():
                score += 0.08
            if target["color"] and item["color"] and target["color"].lower() == item["color"].lower():
                score += 0.06
            item["matchScore"] = round(min(score, 1.0) * 100, 1)
            if item["matchScore"] > 10:
                matches.append(item)
        matches.sort(key=lambda item: item["matchScore"], reverse=True)
        return matches[:5]

    @staticmethod
    def _tokenize(text):
        return [word for word in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(word) > 2]

    @staticmethod
    def _tfidf_vector(tokens, doc_freq, total_docs):
        counts = Counter(tokens)
        total_terms = sum(counts.values()) or 1
        vector = {}
        for token, count in counts.items():
            tf = count / total_terms
            idf = math.log((1 + total_docs) / (1 + doc_freq[token])) + 1
            vector[token] = tf * idf
        return vector

    @staticmethod
    def _cosine_similarity(left, right):
        shared = set(left).intersection(right)
        numerator = sum(left[token] * right[token] for token in shared)
        left_mag = math.sqrt(sum(value * value for value in left.values()))
        right_mag = math.sqrt(sum(value * value for value in right.values()))
        if left_mag == 0 or right_mag == 0:
            return 0.0
        return numerator / (left_mag * right_mag)


STORE = FindItStore(DB_PATH)


class CloudinaryClient:
    def __init__(self):
        self.cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        self.api_key = os.environ.get("CLOUDINARY_API_KEY", "").strip()
        self.api_secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

    @property
    def enabled(self):
        return bool(self.cloud_name and self.api_key and self.api_secret)

    def upload_data_uri(self, data_uri: str):
        if not self.enabled:
            raise ValueError("Image upload is not configured yet.")
        if not data_uri.startswith("data:image/"):
            raise ValueError("Only image uploads are supported.")
        timestamp = str(int(time.time()))
        params_to_sign = f"timestamp={timestamp}{self.api_secret}"
        signature = hashlib.sha1(params_to_sign.encode("utf-8")).hexdigest()
        payload = parse.urlencode({
            "file": data_uri,
            "api_key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
        }).encode("utf-8")
        upload_url = f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/upload"
        req = request.Request(upload_url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with request.urlopen(req, timeout=40) as response:
            result = json.loads(response.read().decode("utf-8"))
        return {
            "secureUrl": result.get("secure_url", ""),
            "publicId": result.get("public_id", ""),
        }


CLOUDINARY = CloudinaryClient()


class FindItHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._common_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api("GET", parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api("POST", parsed)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def handle_api(self, method, parsed):
        try:
            user = self.current_user()
            path = parsed.path.rstrip("/") or "/"
            if path == "/api/session" and method == "GET":
                self.respond_json({"user": STORE.serialize_user(user)})
                return
            if path == "/api/register" and method == "POST":
                payload = self.read_json()
                required = ["full_name", "email", "password"]
                if any(not payload.get(field) for field in required):
                    raise ValueError("Full name, email, and password are required.")
                user = STORE.create_user(payload)
                token = STORE.create_session(user["id"])
                self.set_session_cookie(token)
                self.respond_json({"user": STORE.serialize_user(user)}, status=HTTPStatus.CREATED)
                return
            if path == "/api/login" and method == "POST":
                payload = self.read_json()
                user = STORE.authenticate(payload.get("email", ""), payload.get("password", ""))
                if not user:
                    self.respond_json({"error": "Invalid email or password."}, status=HTTPStatus.UNAUTHORIZED)
                    return
                token = STORE.create_session(user["id"])
                self.set_session_cookie(token)
                self.respond_json({"user": STORE.serialize_user(user)})
                return
            if path == "/api/logout" and method == "POST":
                token = self.current_token()
                if token:
                    STORE.delete_session(token)
                self.send_response(HTTPStatus.OK)
                self._common_headers()
                self.send_header("Set-Cookie", "findit_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            if path.endswith("/my/listings") and method == "GET":
                user = self.require_user()
                listings = STORE.list_listings_for_user(user["id"])
                for listing in listings:
                    listing["permissions"] = STORE.listing_permissions(listing, user)
                self.respond_json({"listings": listings})
                return
            if path.endswith("/my/claims") and method == "GET":
                user = self.require_user()
                self.respond_json({"claims": STORE.list_claims_for_user(user["id"])})
                return
            if path == "/api/listings" and method == "GET":
                qs = parse_qs(parsed.query)
                filters = {key: values[0] for key, values in qs.items()}
                listings = STORE.list_listings(filters)
                for listing in listings:
                    listing["permissions"] = STORE.listing_permissions(listing, user)
                    if not listing["permissions"]["canSeeContact"]:
                        listing["contactPhone"] = "Hidden until verified claim or owner/admin access"
                self.respond_json({"listings": listings})
                return
            if path == "/api/listings" and method == "POST":
                user = self.require_user()
                payload = self.read_json()
                listing = STORE.create_listing(user["id"], payload)
                listing["permissions"] = STORE.listing_permissions(listing, user)
                self.respond_json({"listing": listing}, status=HTTPStatus.CREATED)
                return
            if path == "/api/upload-image" and method == "POST":
                self.require_user()
                payload = self.read_json()
                uploaded = CLOUDINARY.upload_data_uri(payload.get("fileData", ""))
                self.respond_json(uploaded, status=HTTPStatus.CREATED)
                return
            if path.startswith("/api/listings/") and method == "GET":
                listing_id = int(path.split("/")[-1])
                listing = STORE.get_listing(listing_id)
                if not listing:
                    self.respond_json({"error": "Listing not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                listing["permissions"] = STORE.listing_permissions(listing, user)
                if not listing["permissions"]["canSeeContact"]:
                    listing["contactPhone"] = "Hidden until verified claim or owner/admin access"
                self.respond_json({"listing": listing, "matches": STORE.match_listing(listing_id)})
                return
            if path.endswith("/update") and method == "POST":
                user = self.require_user()
                listing_id = int(path.split("/")[-2])
                listing = STORE.get_listing(listing_id)
                if not listing:
                    self.respond_json({"error": "Listing not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                if not STORE.listing_permissions(listing, user)["canEdit"]:
                    raise PermissionError("You cannot edit this listing.")
                updated = STORE.update_listing(listing_id, self.read_json())
                updated["permissions"] = STORE.listing_permissions(updated, user)
                self.respond_json({"listing": updated})
                return
            if path.endswith("/delete") and method == "POST":
                user = self.require_user()
                listing_id = int(path.split("/")[-2])
                listing = STORE.get_listing(listing_id)
                if not listing:
                    self.respond_json({"error": "Listing not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                if not STORE.listing_permissions(listing, user)["canDelete"]:
                    raise PermissionError("You cannot delete this listing.")
                STORE.delete_listing(listing_id)
                self.respond_json({"ok": True})
                return
            if path.endswith("/claim") and method == "POST":
                user = self.require_user()
                listing_id = int(path.split("/")[-2])
                payload = self.read_json()
                listing = STORE.create_claim(listing_id, user["id"], payload.get("proofText", ""))
                listing["permissions"] = STORE.listing_permissions(listing, user)
                self.respond_json({"listing": listing})
                return
            if path.startswith("/api/claims/") and path.endswith("/status") and method == "POST":
                self.require_user(role="admin")
                claim_id = int(path.split("/")[-2])
                listing = STORE.update_claim_status(claim_id, self.read_json().get("status", "pending"))
                listing["permissions"] = STORE.listing_permissions(listing, user)
                self.respond_json({"listing": listing})
                return
            if path.endswith("/status") and method == "POST":
                user = self.require_user(role="admin")
                listing_id = int(path.split("/")[-2])
                payload = self.read_json()
                listing = STORE.update_listing_status(listing_id, payload.get("status", "open"))
                listing["permissions"] = STORE.listing_permissions(listing, user)
                self.respond_json({"listing": listing})
                return
            if path == "/api/analytics" and method == "GET":
                self.require_user(role="admin")
                self.respond_json(STORE.analytics())
                return
            self.respond_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.respond_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except PermissionError as exc:
            self.respond_json({"error": str(exc)}, status=HTTPStatus.UNAUTHORIZED)
        except Exception as exc:
            self.respond_json({"error": f"Server error: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def current_token(self):
        header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get("findit_session")
        return morsel.value if morsel else None

    def current_user(self):
        return STORE.get_session_user(self.current_token())

    def require_user(self, role=None):
        user = self.current_user()
        if not user:
            raise PermissionError("Please sign in to continue.")
        if role and user["role"] != role:
            raise PermissionError("You do not have access to this action.")
        return user

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def set_session_cookie(self, token):
        self._pending_cookie = f"findit_session={token}; Path=/; HttpOnly; SameSite=Lax"

    def respond_json(self, payload, status=HTTPStatus.OK):
        self.send_response(status)
        self._common_headers()
        cookie = getattr(self, "_pending_cookie", None)
        if cookie:
            self.send_header("Set-Cookie", cookie)
            delattr(self, "_pending_cookie")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _common_headers(self):
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), FindItHandler)
    print(f"FindIt running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
