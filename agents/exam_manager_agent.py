import PyPDF2
import docx
from groq import Groq
import json
import re
import os

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set in environment variables")

client = Groq(api_key=GROQ_API_KEY)

class ExamManagerAgent:
    @staticmethod
    def validate_exam_creation(faculty_id, title, duration, passing_score):
        if duration <= 0:
            return False, "Duration must be positive."
        if passing_score < 0 or passing_score > 100:
            return False, "Passing score must be between 0 and 100."
        if not title.strip():
            return False, "Title is required."
        return True, "Valid"

    @staticmethod
    def is_student_eligible(conn, attempt_id):
        return True

    @staticmethod
    def extract_text_from_pdf(file_stream):
        try:
            reader = PyPDF2.PdfReader(file_stream)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            print(f"DEBUG: Extracted {len(text)} chars from PDF")
            return text
        except Exception as e:
            print(f"DEBUG: PDF Extraction Error: {str(e)}")
            return None

    @staticmethod
    def extract_text_from_docx(file_stream):
        try:
            doc = docx.Document(file_stream)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            print(f"DEBUG: Extracted {len(text)} chars from DOCX")
            return text
        except Exception as e:
            print(f"DEBUG: DOCX Extraction Error: {str(e)}")
            return None

    @staticmethod
    def generate_questions_from_text(text, num_questions=5):
        prompt = f"""
        Generate {num_questions} multiple choice questions based on the following syllabus/content:
        {text}

        Strictly format the output as a valid JSON array of objects. Do not wrap it in markdown or code blocks.
        Each object MUST have exactly these keys:
        "question_text"
        "option_a"
        "option_b"
        "option_c"
        "option_d"
        "correct_option" (only "A", "B", "C", or "D")

        CRITICAL: Return ONLY a raw JSON array. No markdown, no triple backticks, no preamble.
        """
        return ExamManagerAgent._call_groq(prompt)

    @staticmethod
    def _call_groq(prompt):
        MODELS_TO_TRY = [
            "llama3-8b-8192",       # fast, free, generous quota
            "llama-3.1-8b-instant", # fallback
            "mixtral-8x7b-32768",   # fallback
        ]
        output = "No output"

        for model in MODELS_TO_TRY:
            try:
                print(f"DEBUG: Trying Groq model '{model}'")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.7
                )
                output = response.choices[0].message.content
                print(f"DEBUG: Groq raw output length: {len(output)}")

                output = output.strip()
                if output.startswith("```"):
                    output = re.sub(r'^```(?:json)?\n?|\n?```$', '', output, flags=re.MULTILINE)

                output = output.strip()
                json_match = re.search(r'\[.*\]', output, re.DOTALL)
                if json_match:
                    output = json_match.group(0)

                questions = json.loads(output)
                print(f"DEBUG: Successfully parsed {len(questions)} questions using '{model}'")
                return questions, None

            except Exception as e:
                err_str = str(e)
                print(f"DEBUG: Error on model '{model}': {err_str}")
                if '429' in err_str or 'rate_limit' in err_str.lower():
                    print(f"DEBUG: Rate limit on '{model}', trying next...")
                    continue
                elif 'model_not_found' in err_str.lower() or '404' in err_str:
                    print(f"DEBUG: Model '{model}' not found, trying next...")
                    continue
                else:
                    return None, f"AI generation error: {err_str[:200]}"

        return None, "All Groq models failed. Please try again in a moment."
