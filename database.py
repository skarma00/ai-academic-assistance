import sqlite3
import json
import os
import hmac
import hashlib
import secrets
from datetime import datetime
from typing import List, Dict, Optional, Any
from config import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            total_pages INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Generated Answers and Schemes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER,
            question TEXT NOT NULL,
            marks INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            scheme_json TEXT,
            diagram_code TEXT,
            sources_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (doc_id) REFERENCES documents (id)
        )
    """)
    
    # Student Evaluations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER,
            question TEXT NOT NULL,
            target_marks REAL NOT NULL,
            marks_awarded REAL NOT NULL,
            student_answer TEXT NOT NULL,
            feedback_json TEXT,
            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES generated_answers (id)
        )
    """)
    
    # Study Bookmarks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            marks INTEGER,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    

    # User accounts for separate student and teacher workspaces.
    # Existing academic tables are preserved; account ownership is added
    # in a later migration step after the login flow is verified.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Safely add user ownership to existing tables.
    # Existing records are preserved with user_id = NULL.

    ownership_tables = [
        "documents",
        "generated_answers",
        "student_evaluations",
        "study_bookmarks"
    ]

    for table in ownership_tables:
        columns = [
            row["name"]
            for row in cursor.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        ]

        if "user_id" not in columns:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"
            )

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_user
        ON documents(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_user
        ON generated_answers(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_evaluations_user
        ON student_evaluations(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user
        ON study_bookmarks(user_id)
    """)

    conn.commit()
    conn.close()


def save_document_record(
    filename: str,
    file_path: str,
    total_pages: int,
    chunk_count: int,
    file_size: int,
    user_id: int
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents
            (filename, file_path, total_pages, chunk_count, file_size, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            filename, file_path, total_pages,
            chunk_count, file_size, user_id
        ))
        doc_id = cursor.lastrowid
        conn.commit()
        return int(doc_id)
    finally:
        conn.close()



def list_documents(user_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM documents
            WHERE user_id = ?
            ORDER BY uploaded_at DESC
        """, (user_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()



def save_generated_answer(
    doc_id: Optional[int],
    question: str,
    marks: int,
    answer_text: str,
    scheme_dict: Dict,
    diagram_code: str,
    sources: List[Dict],
    user_id: int
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Prevent attaching another user's document.
        if doc_id is not None:
            owned_doc = cursor.execute("""
                SELECT id FROM documents
                WHERE id = ? AND user_id = ?
            """, (doc_id, user_id)).fetchone()

            if not owned_doc:
                raise ValueError("Document does not belong to this account.")

        cursor.execute("""
            INSERT INTO generated_answers
            (doc_id, question, marks, answer_text, scheme_json,
             diagram_code, sources_json, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, question, marks, answer_text,
            json.dumps(scheme_dict),
            diagram_code,
            json.dumps(sources),
            user_id
        ))

        answer_id = cursor.lastrowid
        conn.commit()
        return int(answer_id)
    finally:
        conn.close()


def list_recent_answers(
    user_id: int,
    limit: int = 10
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM generated_answers
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

        results = []

        for row in rows:
            item = dict(row)

            try:
                item["scheme"] = json.loads(
                    item["scheme_json"] or "{}"
                )
            except (ValueError, TypeError):
                item["scheme"] = {}

            try:
                item["sources"] = json.loads(
                    item["sources_json"] or "[]"
                )
            except (ValueError, TypeError):
                item["sources"] = []

            results.append(item)

        return results
    finally:
        conn.close()



def save_evaluation(
    answer_id: Optional[int],
    question: str,
    target_marks: float,
    marks_awarded: float,
    student_answer: str,
    feedback: Dict,
    user_id: int
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # An evaluation can only reference an answer owned
        # by the same account.
        if answer_id is not None:
            owned_answer = cursor.execute("""
                SELECT id FROM generated_answers
                WHERE id = ? AND user_id = ?
            """, (answer_id, user_id)).fetchone()

            if not owned_answer:
                raise ValueError("Answer does not belong to this account.")

        cursor.execute("""
            INSERT INTO student_evaluations
            (answer_id, question, target_marks, marks_awarded,
             student_answer, feedback_json, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            answer_id, question, target_marks, marks_awarded,
            student_answer, json.dumps(feedback), user_id
        ))

        evaluation_id = cursor.lastrowid
        conn.commit()
        return int(evaluation_id)
    finally:
        conn.close()



def list_recent_evaluations(
    user_id: int,
    limit: int = 10
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM student_evaluations
            WHERE user_id = ?
            ORDER BY evaluated_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

        results = []

        for row in rows:
            item = dict(row)

            try:
                item["feedback"] = json.loads(
                    item["feedback_json"] or "{}"
                )
            except (ValueError, TypeError):
                item["feedback"] = {}

            results.append(item)

        return results
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")


# -------------------------------------------------------------------------
# Authentication helpers
# -------------------------------------------------------------------------

def _hash_password(password: str, salt_hex: Optional[str] = None):
    """Hash a password with PBKDF2-HMAC-SHA256 and a per-user random salt."""
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        310_000
    )
    return digest.hex(), salt.hex()



def create_user(full_name: str, email: str, password: str, role: str = "student") -> int:
    """Create student accounts. Teacher accounts require a separate protected function."""

    role = (role or "student").strip().lower()

    if role != "student":
        raise ValueError("Teacher accounts must use protected teacher registration.")

    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()

    if not full_name:
        raise ValueError("Please enter your full name.")

    if not email or "@" not in email:
        raise ValueError("Please enter a valid email address.")

    password_hash, password_salt = _hash_password(password)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users
            (full_name, email, password_hash, password_salt, role)
            VALUES (?, ?, ?, ?, 'student')
        """, (full_name, email, password_hash, password_salt))

        conn.commit()
        return int(cursor.lastrowid)

    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists.") from exc

    finally:
        conn.close()


def create_teacher_user(
    full_name: str,
    email: str,
    password: str,
    invite_code: str
) -> int:
    """Create a teacher account only when the protected invite code is valid."""

    expected_code = os.getenv("TEACHER_INVITE_CODE", "")

    if not expected_code:
        raise ValueError("Teacher registration is currently disabled.")

    if not invite_code or not hmac.compare_digest(
        invite_code, expected_code
    ):
        raise ValueError("Invalid teacher registration code.")

    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()

    if not full_name:
        raise ValueError("Please enter your full name.")

    if not email or "@" not in email:
        raise ValueError("Please enter a valid email address.")

    password_hash, password_salt = _hash_password(password)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users
            (full_name, email, password_hash, password_salt, role)
            VALUES (?, ?, ?, ?, 'teacher')
        """, (full_name, email, password_hash, password_salt))

        conn.commit()
        return int(cursor.lastrowid)

    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists.") from exc

    finally:
        conn.close()




def authenticate_user(email: str, password: str):
    """Authenticate a user and return safe account details."""

    email = (email or "").strip().lower()

    if not email or not isinstance(password, str) or len(password) < 8:
        return None

    conn = get_connection()

    try:
        row = conn.execute("""
            SELECT id, full_name, email, password_hash,
                   password_salt, role, is_active
            FROM users
            WHERE email = ?
            LIMIT 1
        """, (email,)).fetchone()

        if not row or not row["is_active"]:
            return None

        candidate_hash, _ = _hash_password(
            password, row["password_salt"]
        )

        if not hmac.compare_digest(
            candidate_hash, row["password_hash"]
        ):
            return None

        return {
            "id": int(row["id"]),
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"]
        }

    finally:
        conn.close()



def get_user_by_id(user_id: int):
    """Return non-sensitive account details for the current session."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id, full_name, email, role, is_active, created_at
            FROM users WHERE id = ?
        """, (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
