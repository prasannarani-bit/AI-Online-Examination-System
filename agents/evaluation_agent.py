class EvaluationAgent:
    @staticmethod
    def evaluate_attempt(conn, attempt_id):
        """
        Calculates score by comparing chosen answers to correct answers.
        Updates the attempt_answers table.
        """
        # Fetch attempt details
        attempt = conn.execute("SELECT exam_id FROM exam_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if not attempt:
            return 0
        
        exam_id = attempt['exam_id']
        
        # Fetch questions and correctness
        query = """
        SELECT a.id, a.selected_option, q.correct_option 
        FROM attempt_answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.attempt_id = ?
        """
        answers = conn.execute(query, (attempt_id,)).fetchall()
        
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
        
        return score_percent
