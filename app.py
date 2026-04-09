from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import jwt
import datetime
import csv
import io
from functools import wraps
import os

from models.database import init_db, get_db_connection, migrate_db
from agents.exam_manager_agent import ExamManagerAgent
from agents.proctor_agent import ProctorAgent
from agents.evaluation_agent import EvaluationAgent
from agents.analytics_agent import AnalyticsAgent
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='frontend', static_url_path='/')
CORS(app) # Enable CORS for all routes
app.config['SECRET_KEY'] = 'super_secret_agentic_key'

@app.route("/")
def home():
    return "App working ✅"

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)


proctor_agent = ProctorAgent()

if not os.path.exists('database.db'):
    init_db()
else:
    migrate_db()  # ensure new profile columns exist on existing databases

STORAGE_DIR = 'internal_storage'
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

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
            # verify user exists
            conn = get_db_connection()
            current_user = conn.execute("SELECT * FROM users WHERE id = ?", (data['user_id'],)).fetchone()
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
    # Accept either 'email' or legacy 'username' field
    email = data.get('email') or data.get('username')
    if not data or not email or not data.get('password'):
        return jsonify({'message': 'Missing credentials'}), 400
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (email,)).fetchone()
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

    # Basic email format check
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'message': 'Please enter a valid email address'}), 400

    # Role-specific required fields
    if data['role'] == 'student':
        if not data.get('full_name'):
            return jsonify({'message': 'Full name is required for students'}), 400
    elif data['role'] == 'faculty':
        if not data.get('full_name'):
            return jsonify({'message': 'Full name is required for faculty'}), 400
        
    conn = get_db_connection()
    existing_user = conn.execute("SELECT * FROM users WHERE username = ?", (email,)).fetchone()
    if existing_user:
        conn.close()
        return jsonify({'message': 'An account with this email already exists'}), 400
        
    try:
        conn.execute(
            """INSERT INTO users (username, password, role, full_name, class_name, roll_number, department)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                email,
                generate_password_hash(data['password']),
                data['role'],
                data.get('full_name', ''),
                data.get('class_name', ''),   # student
                data.get('roll_number', ''),  # student
                data.get('department', '')    # faculty
            )
        )
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'message': 'Error registering user'}), 500
    
    conn.close()
    return jsonify({'message': 'Account created successfully! Please login.'})


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
        'roll_number': current_user['roll_number'] or ''
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
                """INSERT INTO users (username, password, role, full_name, class_name, roll_number, department)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    email,
                    generate_password_hash(data['password']),
                    data['role'],
                    data.get('full_name', ''),
                    data.get('class_name', ''),
                    data.get('roll_number', ''),
                    data.get('department', '')
                )
            )
            conn.commit()
            conn.close()
            return jsonify({'message': 'User created successfully!'})
        except Exception as e:
            conn.close()
            return jsonify({'message': 'Error creating user (email may already exist).'}), 400
            
    users = conn.execute(
        "SELECT id, username, role, full_name, class_name, roll_number, department FROM users ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/admin/proctor_logs', methods=['GET'])
@token_required
def monitor_exams(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    logs = conn.execute("""
        SELECT p.id, p.attempt_id, p.log_type, p.timestamp, p.image_blob, u.username, e.title as exam_title
        FROM proctoring_logs p
        JOIN exam_attempts a ON p.attempt_id = a.id
        JOIN users u ON a.student_id = u.id
        JOIN exams e ON a.exam_id = e.id
        ORDER BY p.timestamp DESC LIMIT 50
    """).fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

# --- FACULTY ROUTES ---
@app.route('/api/faculty/exams', methods=['GET', 'POST'])
@token_required
def faculty_exams(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    if request.method == 'POST':
        data = request.json
        valid, msg = ExamManagerAgent.validate_exam_creation(
            current_user['id'], data.get('title'), int(data.get('duration', 0)), int(data.get('passing_score', 0)))
        if not valid:
            conn.close()
            return jsonify({'message': msg}), 400
            
        cursor = conn.cursor()
        cursor.execute("INSERT INTO exams (title, description, faculty_id, duration_minutes, passing_score) VALUES (?, ?, ?, ?, ?)",
                     (data['title'], data.get('description', ''), current_user['id'], data['duration'], data['passing_score']))
        conn.commit()
        exam_id = cursor.lastrowid
        conn.close()
        return jsonify({'message': 'Exam created!', 'exam_id': exam_id})
        
    exams = conn.execute("SELECT * FROM exams WHERE faculty_id = ? ORDER BY id DESC", (current_user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(e) for e in exams])

@app.route('/api/faculty/exams/<int:exam_id>', methods=['GET'])
@token_required
def get_exam_details(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found'}), 404
        
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    conn.close()
    return jsonify({'exam': dict(exam), 'questions': [dict(q) for q in questions]})

@app.route('/api/faculty/exams/<int:exam_id>/publish', methods=['POST'])
@token_required
def publish_exam(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    conn.execute("UPDATE exams SET is_published = 1 WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Exam Published!'})

@app.route('/api/faculty/exams/<int:exam_id>', methods=['DELETE'])
@token_required
def delete_exam(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found or unauthorized'}), 404
        
    try:
        conn.execute("DELETE FROM proctoring_logs WHERE attempt_id IN (SELECT id FROM exam_attempts WHERE exam_id = ?)", (exam_id,))
        conn.execute("DELETE FROM attempt_answers WHERE attempt_id IN (SELECT id FROM exam_attempts WHERE exam_id = ?)", (exam_id,))
        conn.execute("DELETE FROM exam_attempts WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM questions WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
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
    
    # Verify exam ownership and not published
    exam = conn.execute("SELECT is_published FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
    if not exam or exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot add questions to this exam'}), 400
        
    data = request.json
    conn.execute("""
        INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
    exam = conn.execute("SELECT is_published FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
    if not exam:
        conn.close()
        return jsonify({'message': 'Exam not found'}), 404
    if exam['is_published']:
        conn.close()
        return jsonify({'message': 'Cannot delete questions from a published exam'}), 400
        
    conn.execute("DELETE FROM questions WHERE id = ? AND exam_id = ?", (question_id, exam_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Question removed!'})

@app.route('/api/faculty/exams/<int:exam_id>/upload_csv', methods=['POST'])
@token_required
def upload_csv(current_user, exam_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exam = conn.execute("SELECT is_published FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
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
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        next(csv_input, None) # Skip header
        count = 0
        for row in csv_input:
            if len(row) >= 6:
                conn.execute("""
                    INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (exam_id, row[0], row[1], row[2], row[3], row[4], row[5]))
                count += 1
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
    """Normalizes keys from AI response (e.g., 'optionA' -> 'option_a')"""
    normalized = {}
    key_map = {
        'question': 'question_text',
        'questiontext': 'question_text',
        'text': 'question_text',
        'optiona': 'option_a',
        'option_a': 'option_a',
        'a': 'option_a',
        'optionb': 'option_b',
        'option_b': 'option_b',
        'b': 'option_b',
        'optionc': 'option_c',
        'option_c': 'option_c',
        'c': 'option_c',
        'optiond': 'option_d',
        'option_d': 'option_d',
        'd': 'option_d',
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
    exam = conn.execute("SELECT is_published FROM exams WHERE id = ? AND faculty_id = ?", (exam_id, current_user['id'])).fetchone()
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

        questions, error = ExamManagerAgent.generate_questions_from_text(text_content, num_questions=num_questions)
        
        if error:
            print(f"DEBUG: AI Generation Error: {error}")
            conn.close()
            if 'quota exhausted' in error.lower() or 'resource_exhausted' in error.lower():
                return jsonify({'message': '⚠️ AI quota limit reached. Please wait 1-2 minutes and try again. This is a free-tier API limitation.'}), 429
            return jsonify({'message': f"AI generation failed: {error}"}), 500
            
        if not questions:
            print("DEBUG: AI returned no questions")
            conn.close()
            return jsonify({'message': "AI returned no questions. Try different content."}), 500

        for q_raw in questions:
            q = normalize_keys(q_raw)
            conn.execute("""
                INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (exam_id, q.get('question_text', ''), q.get('option_a', ''), q.get('option_b', ''), 
                  q.get('option_c', ''), q.get('option_d', ''), q.get('correct_option', 'A')))
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
        SELECT a.id, e.title as exam_title, u.username as student_name, a.score, a.status, a.end_time,
               (SELECT COUNT(*) FROM proctoring_logs WHERE attempt_id = a.id) as violation_count
        FROM exam_attempts a
        JOIN exams e ON a.exam_id = e.id
        JOIN users u ON a.student_id = u.id
        WHERE e.faculty_id = ? AND a.status = 'evaluated'
        ORDER BY a.end_time DESC
    """, (current_user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in results])

@app.route('/api/faculty/analytics', methods=['GET'])
@token_required
def faculty_analytics(current_user):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    exams = conn.execute("SELECT id, title FROM exams WHERE faculty_id = ? AND is_published = 1", (current_user['id'],)).fetchall()
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
    available_exams = conn.execute("SELECT id, title, description, duration_minutes, passing_score FROM exams WHERE is_published = 1 ORDER BY id DESC").fetchall()
    past_attempts = conn.execute("""
        SELECT a.id, e.title, a.start_time, a.status, a.score
        FROM exam_attempts a JOIN exams e ON a.exam_id = e.id
        WHERE a.student_id = ? ORDER BY a.id DESC
    """, (current_user['id'],)).fetchall()
    conn.close()
    return jsonify({'available_exams': [dict(e) for e in available_exams], 'past_attempts': [dict(a) for a in past_attempts]})

@app.route('/api/student/exams/<int:exam_id>/start', methods=['POST'])
@token_required
def start_exam(current_user, exam_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur_attempt = conn.execute("SELECT id FROM exam_attempts WHERE student_id = ? AND exam_id = ? AND status = 'in_progress'", 
                               (current_user['id'], exam_id)).fetchone()
    if cur_attempt:
        conn.close()
        return jsonify({'attempt_id': cur_attempt['id']})
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO exam_attempts (exam_id, student_id) VALUES (?, ?)", (exam_id, current_user['id']))
    attempt_id = cursor.lastrowid
    
    questions = conn.execute("SELECT id FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    for q in questions:
        cursor.execute("INSERT INTO attempt_answers (attempt_id, question_id) VALUES (?, ?)", (attempt_id, q['id']))
    
    conn.commit()
    conn.close()
    return jsonify({'attempt_id': attempt_id})

@app.route('/api/student/attempts/<int:attempt_id>', methods=['GET'])
@token_required
def get_attempt(current_user, attempt_id):
    if current_user['role'] != 'student':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    attempt = conn.execute("SELECT * FROM exam_attempts WHERE id = ? AND student_id = ?", (attempt_id, current_user['id'])).fetchone()
    if not attempt or attempt['status'] != 'in_progress':
        conn.close()
        return jsonify({'message': 'Invalid attempt'}), 400
        
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (attempt['exam_id'],)).fetchone()
    # don't return correct option to student!
    questions = conn.execute("SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE exam_id = ?", (exam['id'],)).fetchall()
    
    start_time = datetime.datetime.strptime(attempt['start_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    time_elapsed = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds()
    time_left_seconds = max(0, int(exam['duration_minutes'] * 60 - time_elapsed))
    
    conn.close()
    return jsonify({
        'attempt': dict(attempt),
        'exam': dict(exam),
        'questions': [dict(q) for q in questions],
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
        conn.execute("UPDATE attempt_answers SET selected_option = ? WHERE attempt_id = ? AND question_id = ?",
                     (selected_option, attempt_id, q_id))
    
    conn.execute("UPDATE exam_attempts SET status = 'submitted', end_time = CURRENT_TIMESTAMP WHERE id = ?", (attempt_id,))
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
        WHERE a.id = ? AND a.student_id = ? AND a.status = 'evaluated'
    """, (attempt_id, current_user['id'])).fetchone()
    conn.close()
    if not attempt:
        return jsonify({'message': 'Result not found'}), 404
    return jsonify({'attempt': dict(attempt)})

@app.route('/api/student/proctor_log', methods=['POST'])
@token_required
def proctor_log(current_user):
    # Same as before, but with token auth
    data = request.json
    attempt_id = data.get('attempt_id')
    log_type = data.get('type')
    image_base64 = data.get('image')
    
    should_log = False
    log_reason = ''
    
    if log_type == 'tab_switch':
        should_log = True
        log_reason = 'Tab Switching Detected'
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
        conn.execute("INSERT INTO proctoring_logs (attempt_id, log_type, image_blob) VALUES (?, ?, ?)",
                     (attempt_id, log_type, image_base64))
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
    files = conn.execute("SELECT id, filename, uploaded_at FROM faculty_files WHERE faculty_id = ? ORDER BY id DESC", (current_user['id'],)).fetchall()
    conn.close()
    return jsonify([dict(f) for f in files])

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
    file.save(file_path)
    
    conn = get_db_connection()
    conn.execute("INSERT INTO faculty_files (faculty_id, filename, file_path) VALUES (?, ?, ?)", 
                 (current_user['id'], filename, file_path))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'File uploaded to Internal Storage!'})

@app.route('/api/faculty/storage/files/<int:file_id>', methods=['DELETE'])
@token_required
def delete_storage_file(current_user, file_id):
    if current_user['role'] != 'faculty':
        return jsonify({'message': 'Unauthorized'}), 403
    conn = get_db_connection()
    file_record = conn.execute("SELECT * FROM faculty_files WHERE id = ? AND faculty_id = ?", (file_id, current_user['id'])).fetchone()
    if not file_record:
        conn.close()
        return jsonify({'message': 'File not found or unauthorized'}), 404
        
    try:
        if os.path.exists(file_record['file_path']):
            os.remove(file_record['file_path'])
            
        conn.execute("DELETE FROM faculty_files WHERE id = ?", (file_id,))
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
    file_record = conn.execute("SELECT file_path, filename FROM faculty_files WHERE id = ? AND faculty_id = ?", 
                               (file_id, current_user['id'])).fetchone()
    
    if not file_record:
        conn.close()
        return jsonify({'message': 'File not found'}), 404
        
    file_path = file_record['file_path']
    filename = file_record['filename']
    
    try:
        if filename.endswith('.csv'):
            with open(file_path, 'r', encoding='utf8') as f:
                csv_input = csv.reader(f)
                next(csv_input, None)
                questions_data = [row for row in csv_input if len(row) >= 6]
                
            cursor = conn.cursor()
            cursor.execute("INSERT INTO exams (title, description, faculty_id, duration_minutes, passing_score) VALUES (?, ?, ?, ?, ?)",
                     (title, f"Generated from {filename}", current_user['id'], float(duration), float(passing_score)))
            exam_id = cursor.lastrowid
            
            for row in questions_data:
                cursor.execute("""
                    INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (exam_id, row[0], row[1], row[2], row[3], row[4], row[5]))
                
            conn.commit()
            msg = f"Exam {exam_id} created with {len(questions_data)} CSV questions!"
            
        else:
            with open(file_path, 'r', encoding='utf8') as f:
                text_content = f.read()
                
            questions, error = ExamManagerAgent.generate_questions_from_text(text_content, num_questions=num_questions)
            if error:
                conn.close()
                return jsonify({'message': error}), 500
                
            cursor = conn.cursor()
            cursor.execute("INSERT INTO exams (title, description, faculty_id, duration_minutes, passing_score) VALUES (?, ?, ?, ?, ?)",
                     (title, f"Generated from {filename} via AI", current_user['id'], float(duration), float(passing_score)))
            exam_id = cursor.lastrowid
            
            for q in questions:
                cursor.execute("""
                    INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (exam_id, q.get('question_text', ''), q.get('option_a', ''), q.get('option_b', ''), 
                      q.get('option_c', ''), q.get('option_d', ''), q.get('correct_option', 'A')))
                      
            conn.commit()
            msg = f"Exam created with {len(questions)} AI questions!"
            
    except Exception as e:
        conn.close()
        return jsonify({'message': f'Error: {str(e)}'}), 500
        
    conn.close()
    return jsonify({'message': msg, 'exam_id': exam_id})

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return app.send_static_file(path)
    return app.send_static_file('index.html') # fallback to index

if __name__ == '__main__':
    app.run(debug=True, port=5000)
