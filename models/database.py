import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db_connection():
    """Returns a psycopg2 connection that behaves like sqlite3."""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)
    conn.autocommit = False
    return PGConnection(conn)

class PGConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        sql = self._fix_sql(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return PGCursor(cur, self._conn)

    def cursor(self):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return PGCursor(cur, self._conn)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def executescript(self, sql):
        cur = self._conn.cursor()
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                    self._conn.commit()
                except Exception as e:
                    self._conn.rollback()
                    print(f"Script error (ignored): {e}")

    def _fix_sql(self, sql):
        """Convert SQLite ? to PostgreSQL %s and fix SQLite-specific syntax."""
        sql = sql.replace('?', '%s')
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace('datetime(\'now\', \'-10 minutes\')',
                         'NOW() - INTERVAL \'10 minutes\'')
        return sql

class PGCursor:
    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn

    def execute(self, sql, params=None):
        sql = self._fix_sql(sql)
        if params:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return DictRow(dict(row))

    def fetchall(self):
        rows = self._cur.fetchall()
        return [DictRow(dict(r)) for r in rows]

    @property
    def lastrowid(self):
        self._cur.execute("SELECT lastval()")
        return self._cur.fetchone()[0]

    def close(self):
        self._cur.close()

    def _fix_sql(self, sql):
        sql = sql.replace('?', '%s')
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace("datetime('now', '-10 minutes')",
                         "NOW() - INTERVAL '10 minutes'")
        return sql

class DictRow(dict):
    """Dict that also supports index access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

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
            conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {col_type}")
            conn.commit()
        except Exception as e:
            print(f"Migration note {col}: {e}")

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
        print(f"verification_codes note: {e}")
    conn.close()

def init_db():
    """Initialize all tables in PostgreSQL."""
    conn = get_db_connection()
    tables = [
        """CREATE TABLE IF NOT EXISTS users (
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
        )""",
        """CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            faculty_id INTEGER REFERENCES users(id),
            duration_minutes INTEGER NOT NULL,
            passing_score REAL NOT NULL,
            is_published INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER REFERENCES exams(id),
            question_text TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_option TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS exam_attempts (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER REFERENCES exams(id),
            student_id INTEGER REFERENCES users(id),
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            score REAL,
            status TEXT DEFAULT 'in_progress'
        )""",
        """CREATE TABLE IF NOT EXISTS attempt_answers (
            id SERIAL PRIMARY KEY,
            attempt_id INTEGER REFERENCES exam_attempts(id),
            question_id INTEGER REFERENCES questions(id),
            selected_option TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS proctoring_logs (
            id SERIAL PRIMARY KEY,
            attempt_id INTEGER REFERENCES exam_attempts(id),
            log_type TEXT,
            image_blob TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS faculty_files (
            id SERIAL PRIMARY KEY,
            faculty_id INTEGER REFERENCES users(id),
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS verification_codes (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            purpose TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    ]

    for table_sql in tables:
        try:
            conn.execute(table_sql)
            conn.commit()
            print(f"Table created/verified OK")
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
            print("Default admin created!")
    except Exception as e:
        print(f"Admin creation note: {e}")

    conn.close()
    migrate_db()
