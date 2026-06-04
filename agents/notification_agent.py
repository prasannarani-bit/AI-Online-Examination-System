import os
import requests
from fpdf import FPDF
from datetime import datetime

class NotificationAgent:
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
        pdf.set_line_width(0.5)
        pdf.rect(5, 5, 287, 200)
        pdf.set_line_width(1.0)
        pdf.rect(8, 8, 281, 194)

        images_dir = os.path.join("frontend", "images")
        floral_path = os.path.join(images_dir, "floral_corner.png")
        if os.path.exists(floral_path):
            pdf.image(floral_path, x=12, y=12, w=40)
            pdf.image(floral_path, x=245, y=158, w=40)

        def centered_text(text, font_family, font_style, size, y_pos, color=(0,0,0)):
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
    def _send_email(to_email, subject, body_text, html_body=None,
                    attachment_path=None, attachment_name=None):
        """Send email via Brevo HTTP API — works on Render free tier."""
        api_key = os.environ.get("BREVO_API_KEY", "")
        from_email = os.environ.get("MAIL_EMAIL", "jntugv.assessment@gmail.com")

        if not api_key:
            print("DEBUG: BREVO_API_KEY not set in Render Environment")
            return False

        payload = {
            "sender": {
                "name": "Agentic Exam System",
                "email": from_email
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body_text,
            "htmlContent": html_body if html_body else body_text
        }

        # Attach certificate if provided
        if attachment_path and os.path.exists(attachment_path):
            try:
                import base64
                with open(attachment_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                payload["attachment"] = [{
                    "content": encoded,
                    "name": attachment_name or os.path.basename(attachment_path)
                }]
            except Exception as e:
                print(f"DEBUG: Attachment error: {str(e)}")

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key
        }

        try:
            response = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers=headers,
                timeout=15
            )
            if response.status_code == 201:
                print(f"DEBUG: Email sent successfully to {to_email}")
                return True
            else:
                print(f"DEBUG: Brevo API error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            print(f"DEBUG: Brevo API request failed: {str(e)}")
            return False

    @staticmethod
    def send_verification_code(to_email, code, purpose):
        subject = "Verification Code - Agentic Exam System"
        if purpose == 'reset':
            subject = "Password Reset Code - Agentic Exam System"

        purpose_text = (
            "verify your email for registration"
            if purpose == 'register'
            else "reset your password"
        )

        body_text = f"""
Dear User,

You requested to {purpose_text}.
Your verification code is: {code}

This code expires in 10 minutes.
If you did not request this, ignore this email.

Best regards,
Agentic Exam System Team
        """

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif; line-height:1.6; color:#333;">
            <div style="max-width:600px; margin:0 auto; padding:20px;
                        border:1px solid #ddd; border-radius:10px;">
                <h2 style="color:#1a3c6e; text-align:center;">
                    Agentic Exam System
                </h2>
                <hr style="border:0; border-top:1px solid #eee;">
                <p>Dear User,</p>
                <p>You requested to <strong>{purpose_text}</strong>.</p>
                <div style="background:#f4f4f4; padding:20px; text-align:center;
                            border-radius:5px; margin:20px 0;">
                    <span style="font-size:36px; font-weight:bold;
                                 letter-spacing:8px; color:#1a3c6e;">
                        {code}
                    </span>
                </div>
                <p style="color:#666; font-size:14px;">
                    Expires in <strong>10 minutes</strong>.
                    If you did not request this, ignore this email.
                </p>
                <hr style="border:0; border-top:1px solid #eee;">
                <p style="font-size:12px; color:#888; text-align:center;">
                    Best regards,<br>
                    <strong>Agentic Exam System Team</strong>
                </p>
            </div>
        </body>
        </html>
        """
        return NotificationAgent._send_email(
            to_email, subject, body_text, html_body
        )

    @staticmethod
    def send_exam_result(to_email, student_name, exam_title, score,
                         passing_score, certificate_path=None):
        passed = score >= passing_score
        subject = f"Exam Result: {exam_title}"
        status_text = (
            "CONGRATULATIONS! You have PASSED."
            if passed
            else "Unfortunately, you did not meet the passing score."
        )

        body_text = f"""
Dear {student_name},

Exam: {exam_title}
Score: {score}%
Passing Score: {passing_score}%
Status: {'PASSED' if passed else 'FAILED'}

{status_text}

Best regards,
Agentic Exam System Team
        """

        html_body = f"""
        <html>
        <body style="font-family:Arial,sans-serif; color:#333;">
            <div style="max-width:600px; margin:0 auto; padding:20px;
                        border:1px solid #ddd; border-radius:10px;">
                <h2 style="color:#1a3c6e; text-align:center;">
                    Agentic Exam System
                </h2>
                <hr>
                <p>Dear <strong>{student_name}</strong>,</p>
                <p>Exam: <strong>{exam_title}</strong></p>
                <table style="width:100%; background:#f4f4f4;
                              padding:15px; border-radius:5px;">
                    <tr>
                        <td><strong>Score:</strong></td>
                        <td>{score}%</td>
                    </tr>
                    <tr>
                        <td><strong>Passing Score:</strong></td>
                        <td>{passing_score}%</td>
                    </tr>
                    <tr>
                        <td><strong>Status:</strong></td>
                        <td style="color:{'green' if passed else 'red'};
                                   font-weight:bold;">
                            {'PASSED ✓' if passed else 'FAILED ✗'}
                        </td>
                    </tr>
                </table>
                <p style="margin-top:20px;">{status_text}</p>
                <hr>
                <p style="font-size:12px; color:#888; text-align:center;">
                    Best regards,<br>
                    <strong>Agentic Exam System Team</strong>
                </p>
            </div>
        </body>
        </html>
        """

        attach_path = certificate_path if passed and certificate_path else None
        attach_name = (
            f"Certificate_{exam_title.replace(' ', '_')}.pdf"
            if passed else None
        )

        return NotificationAgent._send_email(
            to_email, subject, body_text,
            html_body, attach_path, attach_name
        )
