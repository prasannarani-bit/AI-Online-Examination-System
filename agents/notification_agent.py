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
    EMAIL_USER = "jntugv.assessment@gmail.com"
    EMAIL_PASS = "wqce lwep ktih snaq"
    
    BG_PATH = os.path.join("internal_storage", "assets", "certificate_bg.png")

    @staticmethod
    def generate_certificate(student_name, exam_title, score, date_str=None):
        """
        Generates a premium PDF certificate matching the new professional design system.
        """
        if not date_str:
            date_str = datetime.now().strftime("%B %d, %Y")
            
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(False) # Prevent multi-page splits
        
        # Colors (RGB)
        PRIMARY_BLUE = (16, 44, 87) # #102C57
        GOLD = (197, 160, 89)       # #C5A059
        TEXT_DARK = (26, 26, 26)   # #1A1A1A
        CREAM = (253, 251, 244)     # #FDFBF4
        LIGHT_BLUE = (26, 60, 110) # #1A3C6E

        # 1. Background Fill
        pdf.set_fill_color(*CREAM)
        pdf.rect(0, 0, 297, 210, 'F')

        # 2. Geometric Shapes (Corner Polygons)
        # Top Right Corner - Shape 2 (Darker Blue Overlay)
        pdf.set_fill_color(*LIGHT_BLUE)
        pdf.polygon([(297+20, -20), (297-80, -20), (297-30, 80), (297+20, 130)], 'F')
        
        # Top Right Corner - Shape 1 (Primary Blue)
        pdf.set_fill_color(*PRIMARY_BLUE)
        pdf.polygon([(297+10, -10), (297-70, -10), (297-20, 70), (297+10, 120)], 'F')
        
        # Bottom Left Corner - Shape 2 (Darker Blue Overlay)
        pdf.set_fill_color(*LIGHT_BLUE)
        pdf.polygon([(-20, 210+20), (100, 210+20), (50, 210-90), (-20, 210-40)], 'F')
        
        # Bottom Left Corner - Shape 1 (Primary Blue)
        pdf.set_fill_color(*PRIMARY_BLUE)
        pdf.polygon([(-10, 210+10), (90, 210+10), (40, 210-80), (-10, 210-30)], 'F')

        # 3. Gold Accent Lines
        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.8)
        # Top Right line
        pdf.line(230, 0, 297, 60)
        # Bottom Left line
        pdf.line(0, 150, 70, 210)

        # 4. Borders
        # Outer Gold Border
        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.5)
        pdf.rect(5, 5, 287, 200)
        # Inner Gold Border
        pdf.set_line_width(1.0)
        pdf.rect(8, 8, 281, 194)

        # 5. Floral Ornaments and Logo
        images_dir = os.path.join("frontend", "images")
        logo_path = os.path.join(images_dir, "jntugv_logo.png")
        floral_path = os.path.join(images_dir, "floral_corner.png")
        
        # Logo removed per user request
        
        if os.path.exists(floral_path):
            # Top-left floral corner
            pdf.image(floral_path, x=12, y=12, w=40)
            # Bottom-right floral corner (we can rotate by drawing mirrored but FPDF image doesn't support rotation easily)
            # For simplicity, we just place it in the other corner
            pdf.image(floral_path, x=245, y=158, w=40)

        # 6. Typography & Content
        def centered_text(text, font_family, font_style, size, y_pos, color=(0, 0, 0)):
            pdf.set_font(font_family, font_style, size)
            pdf.set_text_color(*color)
            pdf.set_xy(0, y_pos)
            pdf.cell(297, 10, text, border=0, ln=1, align='C')

        # University Heading (Restored to Centered)
        centered_text("JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY", "Times", "B", 20, 30, color=PRIMARY_BLUE)
        centered_text("GURAJADA VIZIANAGARAM", "Times", "B", 16, 38, color=PRIMARY_BLUE)
        # Note: y_pos 30/38 provides enough clearance below the blue graphics

        # Certificate Title
        centered_text("CERTIFICATE", "Times", "B", 48, 58, color=PRIMARY_BLUE)
        centered_text("OF ACHIEVEMENT", "Helvetica", "B", 18, 70, color=PRIMARY_BLUE)
        
        # Ornament
        pdf.set_font("Times", "", 24)
        centered_text("- oooo -", "Times", "", 20, 80, color=GOLD)
        
        centered_text("This is to certify that", "Helvetica", "", 16, 95, color=TEXT_DARK)
        
        # Student Name (Large Serif)
        centered_text(student_name, "Times", "BI", 42, 110, color=TEXT_DARK) 
        
        # Achievement Details
        centered_text("has successfully completed the examination for", "Helvetica", "", 16, 140, color=TEXT_DARK)
        centered_text(exam_title, "Helvetica", "B", 24, 152, color=PRIMARY_BLUE)
        
        centered_text(f"with an outstanding score of {score}%", "Helvetica", "I", 14, 165, color=TEXT_DARK)
        
        # 7. Signature Sections
        pdf.set_font("Helvetica", "", 12)
        pdf.set_text_color(*PRIMARY_BLUE)
        
        # Signature Lines
        pdf.set_draw_color(*GOLD)
        pdf.set_line_width(0.5)
        
        # Left Signature (REMOVED)
        # pdf.line(40, 192, 110, 192)
        # pdf.set_xy(40, 193)
        # pdf.set_font("Helvetica", "B", 13)
        # pdf.cell(70, 7, "Chief Academic Officer", border=0, ln=0, align='C')
        # pdf.set_xy(40, 198)
        # pdf.set_font("Helvetica", "", 11)
        # pdf.cell(70, 5, "University Authority", border=0, ln=0, align='C')
        
        # Center Seal (Placeholder)
        pdf.set_draw_color(*PRIMARY_BLUE)
        pdf.set_line_width(0.2)
        # pdf.circle(148.5, 185, 12) # Just for aesthetics
        
        # Right Signature
        pdf.line(187, 192, 257, 192)
        pdf.set_xy(187, 193)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(70, 7, "Registrar", border=0, ln=0, align='C')
        pdf.set_xy(187, 198)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(70, 5, "JNTU-GV", border=0, ln=0, align='C')

        # Date at bottom center
        centered_text(f"Issue Date: {date_str}", "Helvetica", "I", 9, 202, color=(120, 120, 120))
        
        # Ensure temp directory exists
        temp_dir = os.path.join("internal_storage", "temp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        file_path = os.path.join(temp_dir, f"certificate_{student_name.replace(' ', '_')}.pdf")
        pdf.output(file_path)
        return file_path

    @staticmethod
    def send_exam_result(to_email, student_name, exam_title, score, passing_score, certificate_path=None):
        """
        Sends an email with exam results and optional certificate.
        """
        passed = score >= passing_score
        subject = f"Exam Result: {exam_title}"
        
        msg = MIMEMultipart()
        msg['From'] = f"Agentic Exam System <{NotificationAgent.EMAIL_USER}>"
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
                
        try:
            server = smtplib.SMTP(NotificationAgent.SMTP_SERVER, NotificationAgent.SMTP_PORT)
            server.set_debuglevel(1)
            server.starttls()
            server.login(NotificationAgent.EMAIL_USER, NotificationAgent.EMAIL_PASS)
            server.send_message(msg)
            server.quit()
            print(f"DEBUG: Email sent successfully to {to_email}")
            return True
        except Exception as e:
            print(f"DEBUG: Failed to send email: {str(e)}")
            return False

    @staticmethod
    def send_verification_code(to_email, code, purpose):
        """
        Sends a 6-digit verification code for registration or password reset.
        """
        subject = "Verification Code - Agentic Exam System"
        if purpose == 'reset':
            subject = "Password Reset Code - Agentic Exam System"
            
        msg = MIMEMultipart()
        msg['From'] = f"Agentic Exam System <{NotificationAgent.EMAIL_USER}>"
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
        
        # HTML Version for better deliverability and look
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
        
        try:
            server = smtplib.SMTP(NotificationAgent.SMTP_SERVER, NotificationAgent.SMTP_PORT)
            server.set_debuglevel(1)
            server.starttls()
            server.login(NotificationAgent.EMAIL_USER, NotificationAgent.EMAIL_PASS)
            server.send_message(msg)
            server.quit()
            print(f"DEBUG: Verification code sent successfully to {to_email}")
            return True
        except Exception as e:
            print(f"DEBUG: Failed to send verification code: {str(e)}")
            return False
