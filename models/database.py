import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db_connection():
    """Returns a PostgreSQL connection with dict-like row access."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn

def dict_fetchall(cursor):
    """Return all rows as list of dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def dict_fetchone(cursor):
    """Return one row as dict."""
    if cursor.description is None:
        return None
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None

class DictConnection:
    """
    Wrapper around psycopg2 connection to mimic sqlite3's
    dict row_factory and execute/commit/close interface.
    """
    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()

    def execute(self, sql, params=None):
        # Convert SQLite ? placeholders to PostgreSQL %s
        sql = sql.replace('?', '%s')
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return DictCursor(self._cursor)

    def cursor(self):
        return DictCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._cursor.close()
        self._conn.close()

    def executescript(self, sql):
        """Execute multiple SQL statements."""
        self._conn.autocommit = True
        cursor = self._conn.cursor()
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except Exception as e:
                    print(f"Script statement error (ignored): {e}")
        self._conn.autocommit = False

class DictCursor:
    """Wrapper around psycopg2 cursor to return dict rows."""
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s')
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def fetchone(self):
        if self._cursor.description is None:
            return None
        columns = [col[0] for col in self._cursor.description]
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DictRow(dict(zip(columns, row)))

    def fetchall(self):
        if self._cursor.description is None:
            return []
        columns = [col[0] for col in self._cursor.description]
        return [DictRow(dict(zip(columns, row))) for row in self._cursor.fetchall()]

    @property
    def lastrowid(self):
        self._cursor.execute("SELECT lastval()")
        return self._cursor.fetchone()[0]

    def close(self):
        self._cursor.close()

class DictRow(dict):
    """Dict subclass that also supports index access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)

def get_db_connection():
    """Returns a DictConnection wrapping a psycopg2 connection."""
    conn = psycopg2.connect(DATABASE_URL)
    return DictConnection(conn)

def migrate_db():
    """Safely add new columns if they don't exist."""
    conn = get_db_connection()
    
    new_cols = {
        'full_name':       'TEXT',
        'class_name':      'TEXT',
        'roll_number':     'TEXT',
        'department':      'TEXT',
        'is_active':       'INTEGER DEFAULT 1',
        'course_category': 'TEXT',
        'course_name':     'TEXT',
        'year_of_study':   'TEXT',
        'branch':          'TEXT',
        'is_verified':     'INTEGER DEFAULT 0'
    }

    for col, col_type in new_cols.items():
        try:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )
            conn.commit()
        except Exception as e:
            print(f"Migration note for {col}: {e}")

    # Ensure verification_codes table exists
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Exception as e:
        print(f"verification_codes table note: {e}")

    conn.close()

def init_db():
    """Initialize all tables in PostgreSQL."""
    conn = get_db_connection()

    # Create all tables
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            full_name TEXT,
            class_name TEXT,
            roll_number TEXT,
            department TEXT,
            is_active INTEGER DEFAULT 1,
            course_category TEXT,
            course_name TEXT,
            year_of_study TEXT,
            branch TEXT,
            is_verified INTEGER DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            faculty_id INTEGER REFERENCES users(id),
            duration_minutes INTEGER NOT NULL,
            passing_score REAL NOT NULL,
            is_published INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER REFERENCES exams(id),
            question_text TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_option TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_attempts (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER REFERENCES exams(id),
            student_id INTEGER REFERENCES users(id),
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            score REAL,
            status TEXT DEFAULT 'in_progress'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attempt_answers (
            id SERIAL PRIMARY KEY,
            attempt_id INTEGER REFERENCES exam_attempts(id),
            question_id INTEGER REFERENCES questions(id),
            selected_option TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS proctoring_logs (
            id SERIAL PRIMARY KEY,
            attempt_id INTEGER REFERENCES exam_attempts(id),
            log_type TEXT,
            image_blob TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS faculty_files (
            id SERIAL PRIMARY KEY,
            faculty_id INTEGER REFERENCES users(id),
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS verification_codes (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    ]

    for statement in statements:
        try:
            conn.execute(statement)
            conn.commit()
        except Exception as e:
            print(f"Table creation note: {e}")

    # Insert default admin
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = %s",
            ('admin@exam.com',)
        ).fetchone()

        if not existing:
            conn.execute(
                "INSERT INTO users (username, password, role, full_name) VALUES (%s, %s, %s, %s)",
                ('admin@exam.com', generate_password_hash('admin'), 'admin', 'Administrator')
            )
            conn.commit()
            print("Default admin created: admin@exam.com / admin")
    except Exception as e:
        print(f"Admin creation note: {e}")

    conn.close()
    migrate_db()
