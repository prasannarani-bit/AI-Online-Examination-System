from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import jwt
import datetime
import csv
import io
from functools import wraps
import os
import random
import string
from fpdf import FPDF
import traceback

from models.database import init_db, get_db_connection, migrate_db
from agents.exam_manager_agent import ExamManagerAgent
from agents.proctor_agent import ProctorAgent
from agents.evaluation_agent import EvaluationAgent
from agents.analytics_agent import AnalyticsAgent
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)
app.config['SECRET_KEY'] = 'super_secret_agentic_key'

proctor_agent = ProctorAgent()

try:
    init_db()
    migrate_db()
except Exception as e:
    print(f"DB init warning: {e}")

STORAGE_DIR = 'internal_storage'
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

def serialize_row(row):
    """Convert a dict row, formatting any datetime objects as strings."""
    if row is None:
        return None
    result = {}
    for k, v in dict(row).items():
        if hasattr(v, 'strftime'):
            result[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        else:
            result[k] = v
    return result

# --- JWT Authentication Decorator ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            conn = get_db_connection()
            current_user = conn.execute(
                "SELECT * FROM users WHERE id = %s", (data['user_id'],)
            ).fetchone()
            conn.close()
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid or expired!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# --- AUTHENTICATION ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email') or data.get('username')
    if not data or not email or not data.get('password'):
        return jsonify({'message': 'Missing credentials'}), 400

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = %s AND is_active = 1", (email,)
    ).fetchone()
    conn.close()

    if user and check_password_hash(user['password'], data['password']):
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({
            'token': token,
            'role': user['role'],
            'username': user['username'],
            'full_name': user['full_name'] or user['username']
        })
    return jsonify({'message': 'Invalid email or password'}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email') or data.get('username')
    if not data or not email or not data.get('password') or not data.get('role'):
        return jsonify({'message': 'Missing required fields'}), 400

    if data['role'] not in ['student', 'faculty']:
        return jsonify({'message': 'Invalid role specified'}), 400

    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'message': 'Please enter a valid email address'}), 400

    if data['role'] == 'student':
        if not data.get('full_name'):
            return jsonify({'message': 'Full name is required for students'}), 400
    elif data['role'] == 'faculty':
        if not data.get('full_name'):
            return jsonify({'message': 'Full name is required for faculty'}), 400

    verification_code = data.get('verification_code')
    if not verification_code:
        return jsonify({'message': 'Verification code is required'}), 400

    conn = get_db_connection()
    code_record = conn.execute(
        "SELECT * FROM verification_codes WHERE email = %s AND code = %s AND purpose = 'register' AND created_at > NOW() - INTERVAL '10 minutes' ORDER BY id DESC LIMIT 1",
        (email, verification_code)
    ).fetchone()

    if not code_record:
        conn.close()
        return jsonify({'message': 'Invalid or expired verification code'}), 400

    existing_user = conn.execute(
        "SELECT * FROM users WHERE username = %s", (email,)
    ).fetchone()
    if existing_user:
        conn.close()
        return jsonify({'message': 'An account with this email already exists'}), 400

    try:
        conn.execute(
            """INSERT INTO users (username, password, role, full_name, class_name,
               roll_number, department, course_category, course_name,
               year_of_study, branch, is_verified)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                email,
                generate_password_hash(data['password']),
                data['role'],
                data.get('full_name', ''),
                data.get('class_name', ''),
                data.get('roll_number', ''),
                data.get('department', ''),
                data.get('course_category', ''),
                data.get('course_name', ''),
                data.get('year_of_study', ''),
                data.get('branch', ''),
                1
            )
        )
        conn.execute(
            "DELETE FROM verification_codes WHERE id = %s", (code_record['id'],)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error registering user: {str(e)}'}), 500

    conn.close()
    return jsonify({'message': 'Account created successfully! Please login.'})

# --- VERIFICATION & PASSWORD RESET ---
@app.route('/api/auth/send-code', methods=['POST'])
def send_verification_code():
    data = request.json
    email = data.get('email')
    purpose = data.get('purpose', 'register')

    if not email:
        return jsonify({'message': 'Email is required'}), 400

    if purpose == 'reset':
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = %s", (email,)
        ).fetchone()
        conn.close()
        if not user:
            return jsonify({'message': 'No account found with this email address'}), 404

    code = ''.join(random.choices(string.digits, k=6))

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO verification_codes (email, code, purpose) VALUES (%s, %s, %s)",
        (email, code, purpose)
    )
    conn.commit()
    conn.close()

    from agents.notification_agent import NotificationAgent
    success = NotificationAgent.send_verification_code(email, code, purpose)

    if success:
        return jsonify({'message': 'Verification code sent to your email'})
    else:
        return jsonify({'message': 'Failed to send email. Please try again later.'}), 500

@app.route('/api/auth/verify-code', methods=['POST'])
def check_verification_code():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    purpose = data.get('purpose', 'register')
    if not email or not code:
        return jsonify({'message': 'Email and code are required'}), 400
    conn = get_db_connection()
    code_record = conn.execute(
        "SELECT * FROM verification_codes WHERE email = %s AND code = %s AND purpose = %s AND created_at > NOW() - INTERVAL '10 minutes' ORDER BY id DESC LIMIT 1",
        (email, code, purpose)
    ).fetchone()
    conn.close()
    if code_record:
        return jsonify({'message': 'Email verified successfully!', 'verified': True})
    else:
        return jsonify({'message': 'Invalid or expired verification code', 'verified': False}), 400

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('password')

    if not email or not code or not new_password:
        return jsonify({'message': 'Missing email, code, or new password'}), 400

    conn = get_db_connection()
    code_record = conn.execute(
        "SELECT * FROM verification_codes WHERE email = %s AND code = %s AND purpose = 'reset' AND created_at > NOW() - INTERVAL '10 minutes' ORDER BY id DESC LIMIT 1",
        (email, code)
    ).fetchone()

    if not code_record:
        conn.close()
        return jsonify({'message': 'Invalid or expired reset code'}), 400

    try:
        conn.execute(
            "UPDATE users SET password = %s WHERE username = %s",
            (generate_password_hash(new_password), email)
        )
        conn.execute(
            "DELETE FROM verification_codes WHERE id = %s", (code_record['id'],)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error resetting password: {str(e)}'}), 500

    conn.close()
    return jsonify({'message': 'Password reset successful! Please login with your new password.'})

@app.route('/api/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    return jsonify({
        'role': current_user['role'],
        'username': current_user['username'],
        'user_id': current_user['id'],
        'full_name': current_user['full_name'] or current_user['username'],
        'department': current_user['department'] or '',
        'class_name': current_user['class_name'] or '',
        'roll_number': current_user['roll_number'] or '',
        'course_category': current_user['course_category'] or '',
        'course_name': current_user['course_name'] or '',
        'year_of_study': current_user['year_of_study'] or '',
        'branch': current_user['branch'] or ''
    })

# --- ADMIN ROUTES ---
@app.route('/api/admin/users', methods=['GET', 'POST'])
@token_required
def manage_users(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    if request.method == 'POST':
        data = request.json
        email = data.get('email') or data.get('username')
        if not email:
            conn.close()
            return jsonify({'message': 'Email is required'}), 400
        try:
            conn.execute(
                """INSERT INTO users (username, password, role, full_name, class_name,
                   roll_number, department, course_category, course_name,
                   year_of_study, branch)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    email,
                    generate_password_hash(data['password']),
                    data['role'],
                    data.get('full_name', ''),
                    data.get('class_name', ''),
                    data.get('roll_number', ''),
                    data.get('department', ''),
                    data.get('course_category', ''),
                    data.get('course_name', ''),
                    data.get('year_of_study', ''),
                    data.get('branch', '')
                )
            )
            conn.commit()
            conn.close()
            return jsonify({'message': 'User created successfully!'})
        except Exception as e:
            conn.close()
            return jsonify({'message': 'Error creating user (email may already exist).'}), 400

    users = conn.execute(
        "SELECT id, username, role, full_name, class_name, roll_number, department, is_active, course_category, course_name, year_of_study, branch FROM users ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify([serialize_row(u) for u in users])

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE', 'PUT'])
@token_required
def admin_manage_user_by_id(current_user, user_id):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    user = conn.execute(
        "SELECT role FROM users WHERE id = %s", (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({'message': 'User not found'}), 404

    if request.method == 'DELETE':
        if user['role'] == 'admin':
            conn.close()
            return jsonify({'message': 'Admins cannot delete other administrators'}), 403
        conn.execute("UPDATE users SET is_active = 0 WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'User has been deactivated (soft-deleted)'})

    elif request.method == 'PUT':
        data = request.json
        password_clause = ""
        params = [
            data.get('username'),
            data.get('full_name', ''),
            data.get('role', 'student'),
            data.get('department', ''),
            data.get('class_name', ''),
            data.get('roll_number', ''),
            data.get('course_category', ''),
            data.get('course_name', ''),
            data.get('year_of_study', ''),
            data.get('branch', ''),
            data.get('is_active', 1)
        ]

        if data.get('password'):
            password_clause = ", password = %s"
            params.append(generate_password_hash(data['password']))

        params.append(user_id)

        try:
            conn.execute(f"""
                UPDATE users SET
                    username = %s, full_name = %s, role = %s, department = %s,
                    class_name = %s, roll_number = %s, course_category = %s,
                    course_name = %s, year_of_study = %s, branch = %s, is_active = %s
                    {password_clause}
                WHERE id = %s
            """, tuple(params))
            conn.commit()
            conn.close()
            return jsonify({'message': 'User updated successfully!'})
        except Exception as e:
            conn.close()
            return jsonify({'message': f'Error updating user: {str(e)}'}), 400

@app.route('/api/admin/exams', methods=['GET'])
@token_required
def admin_all_exams(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exams = conn.execute("""
        SELECT e.*, u.full_name as faculty_name
        FROM exams e JOIN users u ON e.faculty_id = u.id
        ORDER BY e.id DESC
    """).fetchall()
    conn.close()
    return jsonify([serialize_row(e) for e in exams])

@app.route('/api/admin/attempts', methods=['GET'])
@token_required
def admin_all_attempts(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    attempts = conn.execute("""
        SELECT a.id, a.score, a.status, a.start_time, a.end_time,
               e.title as exam_title, u.full_name as student_name,
               (SELECT COUNT(*) FROM proctoring_logs WHERE attempt_id = a.id) as violation_count
        FROM exam_attempts a
        JOIN exams e ON a.exam_id = e.id
        JOIN users u ON a.student_id = u.id
        ORDER BY a.id DESC
    """).fetchall()
    conn.close()
    return jsonify([serialize_row(a) for a in attempts])

@app.route('/api/admin/files', methods=['GET'])
@token_required
def admin_all_files(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    files = conn.execute("""
        SELECT f.*, u.full_name as faculty_name
        FROM faculty_files f JOIN users u ON f.faculty_id = u.id
        ORDER BY f.id DESC
    """).fetchall()
    conn.close()
    return jsonify([serialize_row(f) for f in files])

@app.route('/api/admin/proctor_logs', methods=['GET'])
@token_required
def monitor_exams(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    logs = conn.execute("""
        SELECT p.id, p.attempt_id, p.log_type, p.timestamp, p.image_blob,
               u.username, e.title as exam_title
        FROM proctoring_logs p
        JOIN exam_attempts a ON p.attempt_id = a.id
        JOIN users u ON a.student_id = u.id
        JOIN exams e ON a.exam_id = e.id
        ORDER BY p.timestamp DESC LIMIT 50
    """).fetchall()
    conn.close()
    return jsonify([serialize_row(l) for l in logs])

@app.route('/api/admin/proctor_logs/<int:log_id>', methods=['DELETE'])
@token_required
def admin_delete_log(current_user, log_id):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    conn.execute("DELETE FROM proctoring_logs WHERE id = %s", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Proctoring log entry deleted successfully'})

# --- FACULTY ROUTES ---
@app.route('/api/faculty/exams', methods=['GET', 'POST'])
@token_required
def faculty_exams(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    if request.method == 'POST':
        if request.is_json:
            data = request.json
        else:
            data = request.form

        title = data.get('title')
        duration = int(data.get('duration', 0))
        passing_score = int(data.get('passing_score', 0))
        description = data.get('description', '')

        valid, msg = ExamManagerAgent.validate_exam_creation(
            current_user['id'], title, duration, passing_score
        )
        if not valid:
            conn.close()
            return jsonify({'message': msg}), 400

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (title, description, faculty_id, duration_minutes, passing_score) VALUES (%s, %s, %s, %s, %s)",
            (title, description, current_user['id'], duration, passing_score)
        )
        conn.commit()
        exam_id = cursor.lastrowid

        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                try:
                    text_content = get_text_from_file(file)
                    if text_content:
                        num_questions = int(data.get('num_questions', 5))
                        questions, error = ExamManagerAgent.generate_questions_from_text(
                            text_content, num_questions=num_questions
                        )
                        if not error and questions:
                            for q_raw in questions:
                                q = normalize_keys(q_raw)
                                cursor.execute("""
                                    INSERT INTO questions (exam_id, question_text, option_a,
                                    option_b, option_c, option_d, correct_option)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                                """, (exam_id, q.get('question_text', ''),
                                      q.get('option_a', ''), q.get('option_b', ''),
                                      q.get('option_c', ''), q.get('option_d', ''),
                                      q.get('correct_option', 'A')))
                            conn.commit()
                            msg = f"Exam created and {len(questions)} AI questions generated!"
                        elif error:
                            msg = f"Exam created, but AI generation failed: {error}"
                    else:
                        msg = "Exam created, but could not read syllabus file content."
                except Exception as e:
                    msg = f"Exam created, but error during AI generation: {str(e)}"
        else:
            msg = 'Exam created!'

        conn.close()
        return jsonify({'message': msg, 'exam_id': exam_id})

    exams = conn.execute(
        "SELECT * FROM exams WHERE faculty_id = %s ORDER BY id DESC",
        (current_user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([serialize_row(e) for e in exams])

@app.route('/api/faculty/exams/<int:exam_id>', methods=['GET'])
@token_required
def get_exam_details(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT * FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found'}), 404
    questions = conn.execute(
        "SELECT * FROM questions WHERE exam_id = %s", (exam_id,)
    ).fetchall()
    conn.close()
    return jsonify({
        'exam': serialize_row(exam),
        'questions': [serialize_row(q) for q in questions]
    })

@app.route('/api/faculty/exams/<int:exam_id>/publish', methods=['POST'])
@token_required
def publish_exam(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    conn.execute(
        "UPDATE exams SET is_published = 1 WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Exam Published!'})

@app.route('/api/faculty/exams/<int:exam_id>', methods=['DELETE'])
@token_required
def delete_exam(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT * FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found or unauthorized'}), 404

    try:
        conn.execute("DELETE FROM proctoring_logs WHERE attempt_id IN (SELECT id FROM exam_attempts WHERE exam_id = %s)", (exam_id,))
        conn.execute("DELETE FROM attempt_answers WHERE attempt_id IN (SELECT id FROM exam_attempts WHERE exam_id = %s)", (exam_id,))
        conn.execute("DELETE FROM exam_attempts WHERE exam_id = %s", (exam_id,))
        conn.execute("DELETE FROM questions WHERE exam_id = %s", (exam_id,))
        conn.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error deleting exam: {str(e)}'}), 500

    conn.close()
    return jsonify({'message': 'Exam deleted successfully'})

@app.route('/api/faculty/exams/<int:exam_id>/questions', methods=['POST'])
@token_required
def add_question(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT is_published FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam or exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot add questions to this exam'}), 400

    data = request.json
    conn.execute("""
        INSERT INTO questions (exam_id, question_text, option_a, option_b,
        option_c, option_d, correct_option)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (exam_id, data['question_text'], data['option_a'], data['option_b'],
          data['option_c'], data['option_d'], data['correct_option']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Question added successfully!'})

@app.route('/api/faculty/exams/<int:exam_id>/questions/<int:question_id>', methods=['DELETE'])
@token_required
def delete_question(current_user, exam_id, question_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT is_published FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found'}), 404
    if exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot delete questions from a published exam'}), 400

    conn.execute(
        "DELETE FROM questions WHERE id = %s AND exam_id = %s", (question_id, exam_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Question removed!'})

@app.route('/api/faculty/exams/<int:exam_id>/upload_csv', methods=['POST'])
@token_required
def upload_csv(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT is_published FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam or exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot modify this exam'}), 400

    if 'file' not in request.files:
        conn.close()
        return jsonify({'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        conn.close()
        return jsonify({'message': 'No selected file'}), 400

    try:

        filename = file.filename.lower()

        if filename.endswith(".csv"):

            stream = io.StringIO(
                file.stream.read().decode("utf-8"),
                newline=None
            )

            csv_input = csv.reader(stream)
            next(csv_input, None)

            count = 0

            for row in csv_input:

                if len(row) >= 6:

                    conn.execute("""
                        INSERT INTO questions
                        (
                            exam_id,
                            question_text,
                            option_a,
                            option_b,
                            option_c,
                            option_d,
                            correct_option
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        exam_id,
                        row[0],
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                        row[5]
                    ))

                    count += 1

        elif filename.endswith(".pdf"):

            text = ExamManagerAgent.extract_text_from_pdf(
                file.stream
            )

            questions, error = (
                ExamManagerAgent.generate_questions_from_text(
                    text,
                    num_questions=5
                )
            )

            if error:
                raise Exception(error)

            count = 0

            for q in questions:

                conn.execute("""
                    INSERT INTO questions
                    (
                        exam_id,
                        question_text,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        correct_option
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    exam_id,
                    q["question_text"],
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["option_d"],
                    q["correct_option"]
                ))

                count += 1

        elif filename.endswith(".txt"):

            text = file.read().decode("utf-8")

            questions, error = (
                ExamManagerAgent.generate_questions_from_text(
                    text,
                    num_questions=5
                )
            )

            if error:
                raise Exception(error)

            count = 0

            for q in questions:

                conn.execute("""
                    INSERT INTO questions
                    (
                        exam_id,
                        question_text,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        correct_option
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    exam_id,
                    q["question_text"],
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["option_d"],
                    q["correct_option"]
                ))

                count += 1

        else:

             raise Exception(
                "Supported formats: CSV, PDF, TXT"
            )

        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error processing file: {str(e)}'}), 400

    conn.close()
    return jsonify({'message': f'Successfully added {count} questions from CSV!'})

def get_text_from_file(file):
    filename = file.filename.lower()
    print(f"DEBUG: Processing file: {filename}")
    file.stream.seek(0)
    if filename.endswith('.pdf'):
        return ExamManagerAgent.extract_text_from_pdf(file.stream)
    elif filename.endswith('.docx'):
        return ExamManagerAgent.extract_text_from_docx(file.stream)
    elif filename.endswith('.txt'):
        try:
            content = file.stream.read().decode("UTF8")
            print(f"DEBUG: Text content length: {len(content)}")
            return content
        except Exception as e:
            print(f"DEBUG: Error decoding text file: {str(e)}")
            return None
    else:
        print(f"DEBUG: Unsupported file extension: {filename}")
        return None

def normalize_keys(q_dict):
    normalized = {}
    key_map = {
        'question': 'question_text',
        'questiontext': 'question_text',
        'text': 'question_text',
        'optiona': 'option_a', 'option_a': 'option_a', 'a': 'option_a',
        'optionb': 'option_b', 'option_b': 'option_b', 'b': 'option_b',
        'optionc': 'option_c', 'option_c': 'option_c', 'c': 'option_c',
        'optiond': 'option_d', 'option_d': 'option_d', 'd': 'option_d',
        'correct': 'correct_option',
        'correctoption': 'correct_option',
        'answer': 'correct_option'
    }
    for k, v in q_dict.items():
        clean_k = k.lower().replace(" ", "").replace("_", "")
        target_k = key_map.get(clean_k, k.lower())
        normalized[target_k] = v
    return normalized

@app.route('/api/faculty/exams/<int:exam_id>/generate_ai', methods=['POST'])
@token_required
def generate_ai(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute(
        "SELECT is_published FROM exams WHERE id = %s AND faculty_id = %s",
        (exam_id, current_user['id'])
    ).fetchone()
    if not exam or exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot modify this exam'}), 400

    if 'file' not in request.files:
        conn.close()
        return jsonify({'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        conn.close()
        return jsonify({'message': 'No selected file'}), 400

    try:
        text_content = get_text_from_file(file)
        if not text_content:
            conn.close()
            return jsonify({'message': 'Could not read file content'}), 400

        try:
            num_questions = int(request.form.get('num_questions', 5))
        except (ValueError, TypeError):
            num_questions = 5

        questions, error = ExamManagerAgent.generate_questions_from_text(
            text_content, num_questions=num_questions
        )

        if error:
            print(f"DEBUG: AI Generation Error: {error}")
            conn.close()
            if 'quota exhausted' in error.lower() or 'resource_exhausted' in error.lower():
                return jsonify({'message': '⚠️ AI quota limit reached. Please wait 1-2 minutes and try again.'}), 429
            return jsonify({'message': f"AI generation failed: {error}"}), 500

        if not questions:
            conn.close()
            return jsonify({'message': "AI returned no questions. Try different content."}), 500

        for q_raw in questions:
            q = normalize_keys(q_raw)
            conn.execute("""
                INSERT INTO questions (exam_id, question_text, option_a, option_b,
                option_c, option_d, correct_option)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (exam_id, q.get('question_text', ''), q.get('option_a', ''),
                  q.get('option_b', ''), q.get('option_c', ''),
                  q.get('option_d', ''), q.get('correct_option', 'A')))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error: {str(e)}'}), 500

    conn.close()
    return jsonify({'message': f'Successfully generated and added {len(questions)} questions!'})

@app.route('/api/faculty/results', methods=['GET'])
@token_required
def faculty_results(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    results = conn.execute("""
        SELECT a.id, e.title as exam_title, u.username as student_name,
               a.score, a.status, a.end_time,
               (SELECT COUNT(*) FROM proctoring_logs WHERE attempt_id = a.id) as violation_count
        FROM exam_attempts a
        JOIN exams e ON a.exam_id = e.id
        JOIN users u ON a.student_id = u.id
        WHERE e.faculty_id = %s AND a.status = 'evaluated'
        ORDER BY a.end_time DESC
    """, (current_user['id'],)).fetchall()
    conn.close()
    return jsonify([serialize_row(r) for r in results])

@app.route('/api/faculty/analytics', methods=['GET'])
@token_required
def faculty_analytics(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exams = conn.execute(
        "SELECT id, title FROM exams WHERE faculty_id = %s AND is_published = 1",
        (current_user['id'],)
    ).fetchall()
    reports = []
    for ex in exams:
        chart_b64 = AnalyticsAgent.generate_exam_performance_chart(conn, ex['id'])
        if chart_b64:
            reports.append({'title': ex['title'], 'chart': chart_b64})
    conn.close()
    return jsonify(reports)

# --- STUDENT ROUTES ---
@app.route('/api/student/dashboard', methods=['GET'])
@token_required
def student_dashboard(current_user):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()

    student_branch = current_user['branch'] or ''
    student_course = current_user['course_name'] or ''

    if student_course.upper() == 'MCA':
        if student_branch and student_branch.upper() != 'IT':
            available_exams = conn.execute("""
                SELECT e.id, e.title, e.description, e.duration_minutes, e.passing_score,
                       (SELECT COUNT(*) FROM exam_attempts WHERE student_id = %s
                        AND exam_id = e.id AND status IN ('submitted', 'evaluated')) as attempt_count
                FROM exams e
                JOIN users f ON e.faculty_id = f.id
                WHERE e.is_published = 1 AND (f.department = %s OR f.department = 'IT')
                ORDER BY e.id DESC
            """, (current_user['id'], student_branch)).fetchall()
        else:
            available_exams = conn.execute("""
                SELECT e.id, e.title, e.description, e.duration_minutes, e.passing_score,
                       (SELECT COUNT(*) FROM exam_attempts WHERE student_id = %s
                        AND exam_id = e.id AND status IN ('submitted', 'evaluated')) as attempt_count
                FROM exams e
                JOIN users f ON e.faculty_id = f.id
                WHERE e.is_published = 1 AND f.department = 'IT'
                ORDER BY e.id DESC
            """, (current_user['id'],)).fetchall()
    else:
        available_exams = conn.execute("""
            SELECT e.id, e.title, e.description, e.duration_minutes, e.passing_score,
                   (SELECT COUNT(*) FROM exam_attempts WHERE student_id = %s
                    AND exam_id = e.id AND status IN ('submitted', 'evaluated')) as attempt_count
            FROM exams e
            JOIN users f ON e.faculty_id = f.id
            WHERE e.is_published = 1 AND f.department = %s
            ORDER BY e.id DESC
        """, (current_user['id'], student_branch)).fetchall()

    past_attempts = conn.execute("""
        SELECT a.id, e.title, a.start_time, a.status, a.score, e.passing_score
        FROM exam_attempts a JOIN exams e ON a.exam_id = e.id
        WHERE a.student_id = %s ORDER BY a.id DESC
    """, (current_user['id'],)).fetchall()
    conn.close()
    return jsonify({
        'available_exams': [serialize_row(e) for e in available_exams],
        'past_attempts': [serialize_row(a) for a in past_attempts]
    })

@app.route('/api/student/exams/<int:exam_id>/start', methods=['POST'])
@token_required
def start_exam(current_user, exam_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    completed_attempt = conn.execute(
        "SELECT id FROM exam_attempts WHERE student_id = %s AND exam_id = %s AND status IN ('submitted', 'evaluated')",
        (current_user['id'], exam_id)
    ).fetchone()
    if completed_attempt:
        conn.close()
        return jsonify({'message': 'Response is submitted'}), 400

    cur_attempt = conn.execute(
        "SELECT id FROM exam_attempts WHERE student_id = %s AND exam_id = %s AND status = 'in_progress'",
        (current_user['id'], exam_id)
    ).fetchone()
    if cur_attempt:
        conn.close()
        return jsonify({'attempt_id': cur_attempt['id']})

    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO exam_attempts
    (
        exam_id,
        student_id
    )
    VALUES (%s,%s)
    RETURNING id
    """, (
        exam_id,
        current_user['id']
    ))
    attempt_row = cursor.fetchone()

    if isinstance(attempt_row, dict):
        attempt_id = attempt_row['id']
    else:
        attempt_id = attempt_row[0]

    conn.commit()
    conn.close()

    return jsonify({
        'attempt_id': attempt_id
    })

@app.route('/api/student/attempts/<int:attempt_id>', methods=['GET'])
@token_required
def get_attempt(current_user, attempt_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    attempt = conn.execute(
        "SELECT * FROM exam_attempts WHERE id = %s AND student_id = %s",
        (attempt_id, current_user['id'])
    ).fetchone()
    if not attempt or attempt['status'] != 'in_progress':
        conn.close()
        return jsonify({'message': 'Invalid attempt'}), 400

    exam = conn.execute(
        "SELECT * FROM exams WHERE id = %s", (attempt['exam_id'],)
    ).fetchone()
    questions = conn.execute(
        "SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE exam_id = %s",
        (exam['id'],)
    ).fetchall()

    start_time = attempt['start_time']
    if isinstance(start_time, str):
        start_time = datetime.datetime.strptime(start_time[:19], '%Y-%m-%d %H:%M:%S')
    start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    time_elapsed = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds()
    time_left_seconds = max(0, int(exam['duration_minutes'] * 60 - time_elapsed))

    conn.close()
    return jsonify({
        'attempt': serialize_row(attempt),
        'exam': serialize_row(exam),
        'questions': [serialize_row(q) for q in questions],
        'time_left_seconds': time_left_seconds
    })

@app.route('/api/student/attempts/<int:attempt_id>/submit', methods=['POST'])
@token_required
def submit_exam(current_user, attempt_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.json
    answers = data.get('answers', {})

    conn = get_db_connection()
    for q_id_str, selected_option in answers.items():
        q_id = int(q_id_str)
        conn.execute(
            "UPDATE attempt_answers SET selected_option = %s WHERE attempt_id = %s AND question_id = %s",
            (selected_option, attempt_id, q_id)
        )

    conn.execute(
        "UPDATE exam_attempts SET status = 'submitted', end_time = CURRENT_TIMESTAMP WHERE id = %s",
        (attempt_id,)
    )
    conn.commit()

    EvaluationAgent.evaluate_attempt(conn, attempt_id)
    conn.commit()
    conn.close()
    return jsonify({'message': 'Exam submitted'})

@app.route('/api/student/attempts/<int:attempt_id>/result', methods=['GET'])
@token_required
def get_result(current_user, attempt_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    attempt = conn.execute("""
        SELECT a.*, e.title, e.passing_score,
               (SELECT COUNT(*) FROM proctoring_logs WHERE attempt_id = a.id) as violation_count
        FROM exam_attempts a JOIN exams e ON a.exam_id = e.id
        WHERE a.id = %s AND a.student_id = %s AND a.status = 'evaluated'
    """, (attempt_id, current_user['id'])).fetchone()
    conn.close()
    if not attempt:
        return jsonify({'message': 'Result not found'}), 404
    return jsonify({'attempt': serialize_row(attempt)})

@app.route('/api/student/exams/<int:exam_id>/question-paper', methods=['GET'])
@token_required
def student_question_paper(current_user, exam_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    attempt = conn.execute(
        "SELECT id FROM exam_attempts WHERE student_id = %s AND exam_id = %s AND status IN ('submitted', 'evaluated')",
        (current_user['id'], exam_id)
    ).fetchone()
    if not attempt:
        conn.close()
        return jsonify({'message': 'You must attempt the exam before viewing the question paper.'}), 403

    exam = conn.execute("SELECT * FROM exams WHERE id = %s", (exam_id,)).fetchone()
    questions = conn.execute(
        "SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE exam_id = %s",
        (exam_id,)
    ).fetchall()
    conn.close()
    return jsonify({
        'exam': serialize_row(exam),
        'questions': [serialize_row(q) for q in questions]
    })

@app.route('/api/student/proctor_log', methods=['POST'])
@token_required
def proctor_log(current_user):
    data = request.json
    attempt_id = data.get('attempt_id')
    log_type = data.get('type')
    image_base64 = data.get('image')

    should_log = False
    log_reason = ''

    if log_type == 'tab_switch':
        should_log = True
        log_reason = 'Tab Switching Detected'
    elif log_type == 'audio_violation':
        should_log = True
        log_reason = 'Unnecessary Sound/Talking Detected'
    elif log_type == 'face_check':
        multiple_faces, no_face, phone_detected = proctor_agent.analyze_frame(image_base64)
        if phone_detected:
            should_log = True
            log_type = 'phone_detected'
            log_reason = 'Mobile phone detected in frame'
        elif multiple_faces:
            should_log = True
            log_type = 'multiple_faces'
            log_reason = 'Multiple faces detected in frame'
        elif no_face:
            should_log = True
            log_type = 'no_face'
            log_reason = 'No face detected in frame'

    if should_log:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO proctoring_logs (attempt_id, log_type, image_blob) VALUES (%s, %s, %s)",
            (attempt_id, log_type, image_base64)
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'warning', 'reason': log_reason})

    return jsonify({'status': 'ok'})

@app.route('/api/faculty/storage/files', methods=['GET'])
@token_required
def get_storage_files(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    files = conn.execute(
        "SELECT id, filename, uploaded_at FROM faculty_files WHERE faculty_id = %s ORDER BY id DESC",
        (current_user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([serialize_row(f) for f in files])

@app.route('/api/faculty/storage/upload', methods=['POST'])
@token_required
def upload_storage_file(current_user):

    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    filename = secure_filename(file.filename)

    faculty_dir = os.path.join(STORAGE_DIR, str(current_user['id']))
    os.makedirs(faculty_dir, exist_ok=True)

    file_path = os.path.join(faculty_dir, filename)

    # REPLACE YOUR OLD content = file.read().decode('utf-8') WITH THIS

    content = ""

    if filename.lower().endswith(".txt"):
        content = file.read().decode("utf-8")

    elif filename.lower().endswith(".pdf"):
        content = ExamManagerAgent.extract_text_from_pdf(file)

        if not content:
            return jsonify({
                "message": "Could not extract text from PDF"
            }), 400

    else:
        return jsonify({
            "message": "Only TXT and PDF files are supported"
        }), 400

    file.seek(0)
    file.save(file_path)

    # PUT THE DATABASE INSERT HERE

    conn = get_db_connection()

    conn.execute(
        """
        INSERT INTO faculty_files
        (
            faculty_id,
            filename,
            file_path,
            file_content
        )
        VALUES (%s,%s,%s,%s)
        """,
        (
            current_user['id'],
            filename,
            file_path,
            content
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        'message': 'File uploaded successfully'
    })
    
@app.route('/api/faculty/storage/files/<int:file_id>', methods=['DELETE'])
@token_required
def delete_storage_file(current_user, file_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    file_record = conn.execute(
        "SELECT * FROM faculty_files WHERE id = %s AND faculty_id = %s",
        (file_id, current_user['id'])
    ).fetchone()
    if not file_record:
        conn.close()
        return jsonify({'message': 'File not found or unauthorized'}), 404

    try:
        if os.path.exists(file_record['file_path']):
            os.remove(file_record['file_path'])
        conn.execute("DELETE FROM faculty_files WHERE id = %s", (file_id,))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error deleting file: {str(e)}'}), 500

    conn.close()
    return jsonify({'message': 'File deleted successfully'})

@app.route('/api/faculty/storage/generate_exam', methods=['POST'])
@token_required
def storage_generate_exam(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.json

    file_id = data.get('file_id')
    title = data.get('title')
    duration = data.get('duration')
    passing_score = data.get('passing_score')
    num_questions = int(data.get('num_questions', 5))

    if not all([file_id, title, duration, passing_score]):
        return jsonify({'message': 'Missing parameters for exam generation'}), 400

    conn = get_db_connection()

    file_record = conn.execute(
        """
        SELECT file_path, filename, file_content
        FROM faculty_files
        WHERE id = %s AND faculty_id = %s
        """,
        (file_id, current_user['id'])
    ).fetchone()

    if not file_record:
        conn.close()
        return jsonify({'message': 'File not found'}), 404

    filename = file_record['filename']
    file_path = file_record['file_path']

    print("DB FILE PATH:", file_path)
    print("FILE EXISTS:", os.path.exists(file_path))

    try:

        # =====================================================
        # CSV FILE
        # =====================================================
        if filename.lower().endswith('.csv'):

            with open(file_path, 'r', encoding='utf-8') as f:
                csv_input = csv.reader(f)
                next(csv_input, None)
                questions_data = [
                    row for row in csv_input
                    if len(row) >= 6
                ]

            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO exams
                (
                    title,
                    description,
                    faculty_id,
                    duration_minutes,
                    passing_score
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                title,
                f"Generated from {filename}",
                current_user['id'],
                float(duration),
                float(passing_score)
            ))

            exam_row = cursor.fetchone()

            if isinstance(exam_row, dict):
                exam_id = exam_row['id']
            else:
                exam_id = exam_row[0]

            for row in questions_data:

                cursor.execute("""
                    INSERT INTO questions
                    (
                        exam_id,
                        question_text,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        correct_option
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    exam_id,
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5]
                ))

            conn.commit()

            msg = (
                f"Exam {exam_id} created with "
                f"{len(questions_data)} CSV questions!"
            )

        # =====================================================
        # AI GENERATED QUESTIONS
        # =====================================================
        else:

            text_content = file_record.get('file_content')

            if not text_content:
                conn.close()
                return jsonify({
                    'message': (
                        'No syllabus content stored. '
                        'Please upload the file again.'
                    )
                }), 400

            print("===================================")
            print("FILE NAME:", filename)
            print("TEXT LENGTH:", len(text_content))
            print("REQUESTED QUESTIONS:", num_questions)
            print("===================================")

            questions, error = (
                ExamManagerAgent.generate_large_question_set(
                    text_content,
                    total_questions=num_questions
                )
            )

            if error:
                conn.close()
                return jsonify({'message': error}), 500

            # Force exact count
            questions = questions[:num_questions]

            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO exams
                (
                    title,
                    description,
                    faculty_id,
                    duration_minutes,
                    passing_score
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                title,
                f"Generated from {filename} via AI",
                current_user['id'],
                float(duration),
                float(passing_score)
            ))

            exam_row = cursor.fetchone()

            if isinstance(exam_row, dict):
                exam_id = exam_row['id']
            else:
                exam_id = exam_row[0]

            for q in questions:

                cursor.execute("""
                    INSERT INTO questions
                    (
                        exam_id,
                        question_text,
                        option_a,
                        option_b,
                        option_c,
                        option_d,
                        correct_option
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    exam_id,
                    q.get('question_text', ''),
                    q.get('option_a', ''),
                    q.get('option_b', ''),
                    q.get('option_c', ''),
                    q.get('option_d', ''),
                    q.get('correct_option', 'A')
                ))

            conn.commit()

            msg = (
                f"Exam created with "
                f"{len(questions)} AI questions!"
            )

    except Exception as e:

        print("FULL ERROR:")
        traceback.print_exc()

        conn.close()

        return jsonify({
            'message': f'Error: {str(e)}'
        }), 500

    conn.close()

    return jsonify({
        'message': msg,
        'exam_id': exam_id
    })
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return app.send_static_file(path)
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
