import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

class AnalyticsAgent:
    @staticmethod
    def generate_exam_performance_chart(conn, exam_id):
        """
        Generate a bar chart of score distributions.
        """
        attempts = conn.execute("SELECT score FROM exam_attempts WHERE exam_id = ? AND status = 'evaluated'", (exam_id,)).fetchall()
        scores = [row['score'] for row in attempts if row['score'] is not None]
        
        if not scores:
            return None
            
        plt.figure(figsize=(6, 4))
        plt.hist(scores, bins=[0, 20, 40, 60, 80, 100], edgecolor='black')
        plt.title('Score Distribution')
        plt.xlabel('Scores')
        plt.ylabel('Number of Students')
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        return f"data:image/png;base64,{img_str}"
