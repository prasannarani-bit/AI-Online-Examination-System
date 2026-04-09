import os
from models.database import init_db, get_db_connection
from werkzeug.security import generate_password_hash

def seed_data():
    if not os.path.exists('database.db'):
        init_db()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create dummy users
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       ('john_faculty', generate_password_hash('password123'), 'faculty'))
        faculty_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       ('alice_student', generate_password_hash('password123'), 'student'))
        student_id = cursor.lastrowid
        
        # Create an exam
        cursor.execute("INSERT INTO exams (title, description, faculty_id, duration_minutes, passing_score, is_published) VALUES (?, ?, ?, ?, ?, ?)",
                       ('Machine Learning Basics', 'A basic test on ML concepts', faculty_id, 30, 50, 1))
        exam_id = cursor.lastrowid
        
        # Add questions
        questions = [
            ("What does ML stand for?", "Machine Learning", "Maximized Logic", "Machine Logistics", "Minimum Loss", "A"),
            ("Which of the following is an unsupervised learning algorithm?", "Linear Regression", "Decision Trees", "K-Means Clustering", "Naive Bayes", "C"),
            ("What is the purpose of an activation function in a neural network?", "To increase training data", "To introduce non-linearity", "To prevent overfitting", "To initialize weights", "B"),
            ("In reinforcement learning, what does the agent seek to maximize?", "Loss", "Error", "Penalty", "Cumulative Reward", "D")
        ]
        
        for q in questions:
            cursor.execute("""
                INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (exam_id, q[0], q[1], q[2], q[3], q[4], q[5]))
        
        conn.commit()
        print("Sample data seeded successfully!")
        print("Faculty credentials - User: john_faculty  | Pass: password123")
        print("Student credentials - User: alice_student | Pass: password123")

    except Exception as e:
        print("Error seeding data (possibly already seeded):", e)
    finally:
        conn.close()

if __name__ == "__main__":
    seed_data()
