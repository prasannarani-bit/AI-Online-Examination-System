import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db():
    """Safely add new profile columns to an existing database without dropping data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Get existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_cols = {row['name'] for row in cursor.fetchall()}
    new_cols = {
        'full_name':   'TEXT',
        'class_name':  'TEXT',
        'roll_number': 'TEXT',
        'department':  'TEXT',
    }
    for col, col_type in new_cols.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            print(f"DB migration: added column '{col}' to users table.")
    conn.commit()
    conn.close()

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    conn = get_db_connection()
    conn.executescript(schema_sql)
    
    # insert default admin (email: admin@exam.com / password: admin)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", ('admin@exam.com',))
    admin = cursor.fetchone()
    if not admin:
        # Also keep legacy 'admin' username working if it exists
        cursor.execute("SELECT * FROM users WHERE username = ?", ('admin',))
        legacy = cursor.fetchone()
        if not legacy:
            cursor.execute(
                "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                ('admin@exam.com', generate_password_hash('admin'), 'admin', 'Administrator')
            )
    
    conn.commit()
    conn.close()
    migrate_db()
