import threading
from agents.notification_agent import NotificationAgent

class EvaluationAgent:
    @staticmethod
    def _trigger_notification_background(student_name, student_email, exam_title, score_percent, passing_score):
        """
        Helper method to run notification logic in the background.
        """
        try:
            certificate_path = None
            if score_percent >= passing_score:
                certificate_path = NotificationAgent.generate_certificate(student_name, exam_title, score_percent)
                
            NotificationAgent.send_exam_result(
                student_email, 
                student_name, 
                exam_title, 
                score_percent, 
                passing_score, 
                certificate_path
            )
        except Exception as e:
            print(f"DEBUG: Background notification failed: {str(e)}")

    @staticmethod
    def evaluate_attempt(conn, attempt_id):
        """
        Calculates score by comparing chosen answers to correct answers.
        Updates the attempt_answers table and sends result email.
        """
        # Fetch attempt details with student and exam information
        query = """
            SELECT a.exam_id, a.student_id, e.title as exam_title, e.passing_score, 
                   u.username as student_email, u.full_name as student_name
            FROM exam_attempts a
            JOIN exams e ON a.exam_id = e.id
            JOIN users u ON a.student_id = u.id
            WHERE a.id = ?
        """
        attempt = conn.execute(query, (attempt_id,)).fetchone()
        
        if not attempt:
            return 0
        
        exam_id = attempt['exam_id']
        
        # Fetch questions and correctness
        query_answers = """
            SELECT a.id, a.selected_option, q.correct_option 
            FROM attempt_answers a
            JOIN questions q ON a.question_id = q.id
            WHERE a.attempt_id = ?
        """
        answers = conn.execute(query_answers, (attempt_id,)).fetchall()
        
        total_questions = len(answers)
        correct_count = 0
        
        for ans in answers:
            is_correct = 1 if ans['selected_option'] == ans['correct_option'] else 0
            if is_correct:
                correct_count += 1
                
            conn.execute("UPDATE attempt_answers SET is_correct = ? WHERE id = ?", (is_correct, ans['id']))
            
        score_percent = int((correct_count / total_questions * 100)) if total_questions > 0 else 0
        
        # update attempt
        conn.execute("UPDATE exam_attempts SET score = ?, status = 'evaluated' WHERE id = ?", (score_percent, attempt_id))
        
        # --- TRIGGER NOTIFICATION ASYNCHRONOUSLY ---
        student_name = attempt['student_name'] or attempt['student_email']
        student_email = attempt['student_email']
        exam_title = attempt['exam_title']
        passing_score = attempt['passing_score']
        
        thread = threading.Thread(
            target=EvaluationAgent._trigger_notification_background,
            args=(student_name, student_email, exam_title, score_percent, passing_score)
        )
        thread.daemon = True
        thread.start()
            
        return score_percent
