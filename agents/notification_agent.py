import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from fpdf import FPDF
from datetime import datetime

class NotificationAgent:
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    EMAIL_USER = os.environ.get("MAIL_EMAIL", "")
    EMAIL_PASS = os.environ.get("MAIL_PASSWORD", "")
    
    BG_PATH = os.path.join("internal_storage", "assets", "certificate_bg.png")

    @staticmethod
    def generate_certificate(student_name, exam_title, score, date_str=None):
        if not date_str:
            date_str = datetime.now().strftime("%B %d, %Y")
            
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(False)
        
        PRIMARY_BLUE = (16, 44, 87)
        GOLD = (197, 160, 89)
        TEXT_DARK = (26, 26, 26)
        CREAM = (253, 251, 244)
        LIGHT_BLUE = (26, 60, 110)

        pdf.set_fill_color(*CREAM)
        pdf.rect(0, 0, 297, 210, 'F')

        pdf.set_fill_color(*LIGHT_BLUE)
        pdf.polygon([(297+20, -20), (297-80, -20), (297-30, 80), (297+20, 130)], 'F')
        
        pdf.set_fill_color(*PRIMARY_BLUE)
        pdf.polygon([(297+10, -10), (297-70, -10), (297-20, 70), (297+10, 120)], 'F')
        
        pdf.set_fill_color(*LIGHT_BLUE)
        pdf.polygon([(-20, 210+20), (100, 210+20), (50, 210-90), (-20, 210-40)], 'F')
        
        pdf.set_fill_color(*PRIMARY_BLUE)
        pdf.polygon([(-10, 210+10), (90, 210+10), (40, 210-80), (-10, 210-30)], 'F')

        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.8)
        pdf.line(230, 0, 297, 60)
        pdf.line(0, 150, 70, 210)

        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.5)
        pdf.rect(5, 5, 287, 200)
        pdf.set_line_width(1.0)
        pdf.rect(8, 8, 281, 194)

        images_dir = os.path.join("frontend", "images")
        floral_path = os.path.join(images_dir, "floral_corner.png")
        
        if os.path.exists(floral_path):
            pdf.image(floral_path, x=12, y=12, w=40)
            pdf.image(floral_path, x=245, y=158, w=40)

        def centered_text(text, font_family, font_style, size, y_pos, color=(0, 0, 0)):
            pdf.set_font(font_family, font_style, size)
            pdf.set_text_color(*color)
            pdf.set_xy(0, y_pos)
            pdf.cell(297, 10, text, border=0, ln=1, align='C')

        centered_text("JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY", "Times", "B", 20, 30, color=PRIMARY_BLUE)
        centered_text("GURAJADA VIZIANAGARAM", "Times", "B", 16, 38, color=PRIMARY_BLUE)
        centered_text("CERTIFICATE", "Times", "B", 48, 58, color=PRIMARY_BLUE)
        centered_text("OF ACHIEVEMENT", "Helvetica", "B", 18, 70, color=PRIMARY_BLUE)
        centered_text("- oooo -", "Times", "", 20, 80, color=GOLD)
        centered_text("This is to certify that", "Helvetica", "", 16, 95, color=TEXT_DARK)
        centered_text(student_name, "Times", "BI", 42, 110, color=TEXT_DARK) 
        centered_text("has successfully completed the examination for", "Helvetica", "", 16, 140, color=TEXT_DARK)
        centered_text(exam_title, "Helvetica", "B", 24, 152, color=PRIMARY_BLUE)
        centered_text(f"with an outstanding score of {score}%", "Helvetica", "I", 14, 165, color=TEXT_DARK)

        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.5)
        pdf.line(187, 192, 257, 192)
        pdf.set_xy(187, 193)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(70, 7, "Registrar", border=0, ln=0, align='C')
        pdf.set_xy(187, 198)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(70, 5, "JNTU-GV", border=0, ln=0, align='C')

        centered_text(f"Issue Date: {date_str}", "Helvetica", "I", 9, 202, color=(120, 120, 120))
        
        temp_dir = os.path.join("internal_storage", "temp")
        os.makedirs(temp_dir, exist_ok=True)
            
        file_path = os.path.join(temp_dir, f"certificate_{student_name.replace(' ', '_')}.pdf")
        pdf.output(file_path)
        return file_path

    @staticmethod
    def _send_email(msg):
        """Central email sending method with proper error handling."""
        email_user = os.environ.get("MAIL_EMAIL", "")
        email_pass = os.environ.get("MAIL_PASSWORD", "")

        if not email_user or not email_pass:
            print("DEBUG: MAIL_EMAIL or MAIL_PASSWORD environment variable not set")
            return False

        try:
            server = smtplib.SMTP(NotificationAgent.SMTP_SERVER, NotificationAgent.SMTP_PORT)
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
            print(f"DEBUG: Email sent successfully to {msg['To']}")
            return True
        except smtplib.SMTPAuthenticationError:
            print("DEBUG: Gmail authentication failed — check MAIL_EMAIL and MAIL_PASSWORD in Render Environment")
            return False
        except smtplib.SMTPException as e:
            print(f"DEBUG: SMTP error: {str(e)}")
            return False
        except Exception as e:
            print(f"DEBUG: Failed to send email: {str(e)}")
            return False

    @staticmethod
    def send_exam_result(to_email, student_name, exam_title, score, passing_score, certificate_path=None):
        passed = score >= passing_score
        subject = f"Exam Result: {exam_title}"
        
        email_user = os.environ.get("MAIL_EMAIL", "")
        msg = MIMEMultipart()
        msg['From'] = f"Agentic Exam System <{email_user}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        status_text = "CONGRATULATIONS! You have PASSED." if passed else "Unfortunately, you did not meet the passing score this time."
        
        body = f"""
        Dear {student_name},

        You have completed the exam: {exam_title}.

        Results:
        - Score: {score}%
        - Passing Score: {passing_score}%
        - Status: {'PASSED' if passed else 'FAILED'}

        {status_text}

        Best regards,
        Agentic Exam System Team
        """
        msg.attach(MIMEText(body, 'plain'))
        
        if passed and certificate_path and os.path.exists(certificate_path):
            try:
                with open(certificate_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename=Certificate_{exam_title.replace(' ', '_')}.pdf",
                )
                msg.attach(part)
            except Exception as e:
                print(f"DEBUG: Error attaching certificate: {str(e)}")
                
        return NotificationAgent._send_email(msg)

    @staticmethod
    def send_verification_code(to_email, code, purpose):
        subject = "Verification Code - Agentic Exam System"
        if purpose == 'reset':
            subject = "Password Reset Code - Agentic Exam System"

        email_user = os.environ.get("MAIL_EMAIL", "")
        msg = MIMEMultipart()
        msg['From'] = f"Agentic Exam System <{email_user}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        purpose_text = "verify your email address for registration" if purpose == 'register' else "reset your password"
        
        body = f"""
        Dear User,

        You have requested to {purpose_text}.

        Your verification code is:

        -------------------------
        {code}
        -------------------------

        This code will expire in 10 minutes. If you did not request this, please ignore this email.

        Best regards,
        Agentic Exam System Team
        """
        msg.attach(MIMEText(body, 'plain'))
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #1a3c6e; text-align: center;">Agentic Exam System</h2>
                <hr style="border: 0; border-top: 1px solid #eee;">
                <p>Dear User,</p>
                <p>You have requested to <strong>{purpose_text}</strong>.</p>
                <div style="background-color: #f4f4f4; padding: 20px; text-align: center; border-radius: 5px; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #1a3c6e;">{code}</span>
                </div>
                <p style="color: #666; font-size: 14px;">This code will expire in <strong>10 minutes</strong>. If you did not request this, please ignore this email.</p>
                <hr style="border: 0; border-top: 1px solid #eee;">
                <p style="font-size: 12px; color: #888; text-align: center;">
                    Best regards,<br>
                    <strong>Agentic Exam System Team</strong>
                </p>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))
        
        return NotificationAgent._send_email(msg)
