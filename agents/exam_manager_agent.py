import PyPDF2
import docx
from groq import Groq
import json
import re
import os
import math

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
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"

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
    def split_text_into_chunks(text, chunk_size=3000):

        chunks = []

        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])

        return chunks
        
    @staticmethod
    def generate_questions_from_text(text, num_questions=5):
        text = text[:6000]

        print("TEXT SENT TO AI:", len(text))
        chunks = ExamManagerAgent.split_text_into_chunks(text)
        MAX_CHUNKS = 2

        if len(chunks) > MAX_CHUNKS:
            chunks = chunks[:MAX_CHUNKS]

        all_questions = []

        questions_per_chunk = max(
            1,
            math.ceil(num_questions / len(chunks))
        )

        print(f"DEBUG: Total chunks = {len(chunks)}")
        print("AI INPUT LENGTH:", len(text))

        for chunk in chunks:

            prompt = f"""
    Generate EXACTLY {questions_per_chunk} multiple-choice questions from the syllabus/content below.

    SYLLABUS:
    {chunk}

    STRICT RULES:

    1. Return ONLY valid JSON.
    2. No markdown.
    3. No explanations.
    4. No code blocks.

    Each question must contain:

    question_text
    option_a
    option_b
    option_c
    option_d
    correct_option

    correct_option must be A, B, C or D.

    Return ONLY a JSON array.
    """

            questions, error = ExamManagerAgent._call_groq(
                prompt,
                questions_per_chunk
            )

            if questions:
                all_questions.extend(questions)

        all_questions = all_questions[:num_questions]

        print(
            f"DEBUG: Final question count = "
            f"{len(all_questions)}"
        )

        return all_questions, None
    @staticmethod
    def generate_large_question_set(text, total_questions=50):

        all_questions = []

        batch_size = 5

        while len(all_questions) < total_questions:

            remaining = total_questions - len(all_questions)

            current_batch = min(batch_size, remaining)

            questions, error = (
                ExamManagerAgent.generate_questions_from_text(
                    text,
                    num_questions=current_batch
                )
            )

            if error:
                return None, error

            all_questions.extend(questions)

            print(
                f"DEBUG: Generated {len(all_questions)} "
                f"of {total_questions} questions"
            )

        return all_questions[:total_questions], None

    @staticmethod
    def _call_groq(prompt, num_questions):

        MODELS_TO_TRY = [
            "llama-3.1-8b-instant"
        ]

        output = "No output"

        for model in MODELS_TO_TRY:

            try:

                print(f"DEBUG: Trying Groq model '{model}'")

                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=4000,
                    temperature=0.3
                )

                output = response.choices[0].message.content

                print(
                    f"DEBUG: Groq raw output length: {len(output)}"
                )

                output = output.strip()

                if output.startswith("```"):
                    output = re.sub(
                        r'^```(?:json)?\n?|\n?```$',
                        '',
                        output,
                        flags=re.MULTILINE
                    )

                output = output.strip()

                json_match = re.search(
                    r'\[.*\]',
                    output,
                    re.DOTALL
                )

                if json_match:
                    output = json_match.group(0)

                questions = json.loads(output)

                if not isinstance(questions, list):
                    raise ValueError(
                        "AI response is not a JSON array"
                    )

                # Force exact count
                if len(questions) > num_questions:

                    print(
                        f"DEBUG: AI returned {len(questions)} "
                        f"questions, trimming to {num_questions}"
                    )

                    questions = questions[:num_questions]

                if len(questions) < num_questions:

                    return (
                        None,
                        f"AI generated only "
                        f"{len(questions)} questions "
                        f"instead of {num_questions}"
                    )

                print(
                    f"DEBUG: Successfully parsed "
                    f"{len(questions)} questions "
                    f"using '{model}'"
                )

                return questions, None

            except Exception as e:

                err_str = str(e)

                print(
                    f"DEBUG: Error on model '{model}': "
                    f"{err_str}"
                )

                if (
                    '429' in err_str
                    or 'rate_limit' in err_str.lower()
                ):

                    print(
                        f"DEBUG: Rate limit on '{model}', "
                        f"trying next..."
                    )

                    continue

                elif (
                    'model_not_found' in err_str.lower()
                    or '404' in err_str
                ):

                    print(
                        f"DEBUG: Model '{model}' not found, "
                        f"trying next..."
                    )

                    continue

                else:

                    return (
                        None,
                        f"AI generation error: {err_str[:200]}"
                    )

        return None, (
            "All Groq models failed. "
            "Please try again in a moment."
        )
