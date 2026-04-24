import PyPDF2
import docx
import io
from google import genai
import json
import re
import time
import os

API_KEY = os.environ.get("API_KEY")
client = genai.Client(api_key=API_KEY)

class ExamManagerAgent:
    @staticmethod
    def validate_exam_creation(faculty_id, title, duration, passing_score):
        """Validates if an exam can be created."""
        if duration <= 0:
            return False, "Duration must be positive."
        if passing_score < 0 or passing_score > 100:
            return False, "Passing score must be between 0 and 100."
        if not title.strip():
            return False, "Title is required."
        return True, "Valid"

    @staticmethod
    def is_student_eligible(conn, attempt_id):
        # Additional checks can go here
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
        
        Strictly format the output as a valid JSON array of objects. Do not wrap it in markdown block quotes.
        Each object MUST have the following keys exactly:
        "question_text"
        "option_a"
        "option_b"
        "option_c"
        "option_d"
        "correct_option" (only "A", "B", "C", or "D")
        """
        return ExamManagerAgent._call_gemini(prompt)

    @staticmethod
    def _call_gemini(prompt):
        # List of models to try in order, from lightest to heaviest
        MODELS_TO_TRY = [
            'gemini-2.0-flash-lite',
            'gemini-2.0-flash',
            'gemini-2.5-flash',
        ]
        MAX_RETRIES = 3
        RETRY_DELAY = 12  # seconds to wait between retries

        prompt += "\n\nCRITICAL: Return ONLY a raw JSON array. No markdown, no triple backticks, no preamble."
        output = "No output"

        for model in MODELS_TO_TRY:
            for attempt in range(MAX_RETRIES):
                try:
                    print(f"DEBUG: Trying model '{model}', attempt {attempt + 1}")
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt
                    )
                    output = response.text
                    print(f"DEBUG: Gemini raw output length: {len(output)}")

                    output = output.strip()
                    if output.startswith("```"):
                        output = re.sub(r'^```(?:json)?\n?|\n?```$', '', output, flags=re.MULTILINE)

                    output = output.strip()
                    json_match = re.search(r'\[.*\]', output, re.DOTALL)
                    if json_match:
                        output = json_match.group(0)

                    questions = json.loads(output)
                    print(f"DEBUG: Successfully parsed {len(questions)} questions using model '{model}'")
                    return questions, None

                except Exception as e:
                    err_str = str(e)
                    if '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str:
                        print(f"DEBUG: Quota exhausted on model '{model}', attempt {attempt + 1}. Waiting {RETRY_DELAY}s...")
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAY)
                        else:
                            print(f"DEBUG: All retries failed for model '{model}'. Trying next model...")
                            break  # Try next model
                    elif '404' in err_str or 'NOT_FOUND' in err_str:
                        print(f"DEBUG: Model '{model}' not found. Trying next model...")
                        break  # Try next model immediately
                    else:
                        print(f"DEBUG: AI Error on model '{model}': {err_str}")
                        raw_hint = output[:100]
                        return None, f"AI generation error: {err_str[:200]} (Raw start: {raw_hint})"

        return None, (
            "AI quota exhausted on all available models. "
            "Please wait 1-2 minutes and try again. "
            "This is a limitation of the free Gemini API tier."
        )
