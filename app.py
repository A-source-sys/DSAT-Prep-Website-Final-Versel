from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import uuid
import random
import json
import os
import shutil
from pathlib import Path

# --------------------
# App Setup
# --------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DB_PATH = BASE_DIR / "instance" / "sat_practice.db"
ROOT_DB_PATH = BASE_DIR / "sat_practice.db"

def resolve_db_path():
    if os.getenv("VERCEL"):
        target = Path("/tmp") / "sat_practice.db"
        if not target.exists():
            source = None
            if INSTANCE_DB_PATH.exists():
                source = INSTANCE_DB_PATH
            elif ROOT_DB_PATH.exists():
                source = ROOT_DB_PATH
            if source is not None:
                shutil.copyfile(source, target)
            else:
                target.touch()
        return target
    if ROOT_DB_PATH.exists():
        return ROOT_DB_PATH
    if INSTANCE_DB_PATH.exists():
        return INSTANCE_DB_PATH
    return ROOT_DB_PATH

DB_PATH = resolve_db_path()

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --------------------
# In-Memory Session Store
# --------------------
SESSION_QUESTIONS_SEEN = {}

def get_or_create_session():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    if session["session_id"] not in SESSION_QUESTIONS_SEEN:
        SESSION_QUESTIONS_SEEN[session["session_id"]] = set()
    return session["session_id"]

def mark_question_seen(session_id, question_id):
    SESSION_QUESTIONS_SEEN.setdefault(session_id, set()).add(question_id)

def has_seen_question(session_id, question_id):
    return question_id in SESSION_QUESTIONS_SEEN.get(session_id, set())

# --------------------
# Models
# --------------------
class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(20), nullable=False)      # math / english
    subcategory = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False)
    stimulus = db.Column(db.Text, nullable=True)
    prompt = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(200), nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    answer_options = db.Column(db.Text, nullable=True)  # JSON-encoded

class AnswerLog(db.Model):
    __tablename__ = "answer_logs"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False)
    question_id = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)

# --------------------
# Utility Functions
# --------------------
def adjust_difficulty(current_difficulty, correct, total):
    accuracy = correct / total
    if accuracy >= 0.8:
        return min(current_difficulty + 1, 3)
    elif accuracy <= 0.4:
        return max(current_difficulty - 1, 1)
    return current_difficulty

def format_questions(questions):
    formatted = []
    for q in questions:
        # Parse answer options for English MCQs
        if q.answer_options:
            try:
                choices = list(json.loads(q.answer_options).keys())
            except Exception:
                choices = ["A", "B", "C", "D"]
        else:
            choices = ["A", "B", "C", "D"]

        formatted.append({
            "id": q.id,
            "stimulus": q.stimulus or "",
            "prompt": q.prompt,
            "difficulty": q.difficulty,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "choices": choices
        })
    return formatted

# --------------------
# Routes
# --------------------
@app.route("/debug/subcategories")
def debug_subcategories():
    rows = db.session.query(Question.subcategory).distinct().all()
    return jsonify([r[0] for r in rows])

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json()
    subcategory = data.get("subcategory")
    session_id = get_or_create_session()
    difficulty = session.get("current_difficulty", 2)

    # Fetch questions strictly by subcategory + difficulty
    all_questions = Question.query.filter_by(
        subcategory=subcategory,
        difficulty=difficulty
    ).all()

    unseen = [q for q in all_questions if not has_seen_question(session_id, q.id)]
    questions = random.sample(unseen, min(5, len(unseen)))

    for q in questions:
        mark_question_seen(session_id, q.id)

    session["current_difficulty"] = difficulty

    return jsonify({
        "difficulty": difficulty,
        "questions": format_questions(questions)
    })

@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    subcategory = data.get("subcategory")
    answers = data.get("answers", [])

    session_id = get_or_create_session()
    current_difficulty = session.get("current_difficulty", 2)
    correct_count = 0
    valid_answers = []

    for a in answers:
        q_id = a.get("id") or a.get("question_id")
        user_answer = str(a.get("user_answer"))
        correct_answer = str(a.get("correct_answer"))
        if q_id is None:
            continue
        is_correct = user_answer == correct_answer
        if is_correct:
            correct_count += 1
        valid_answers.append((q_id, is_correct))

    # Log answers
    for q_id, is_correct in valid_answers:
        log = AnswerLog(session_id=session_id, question_id=q_id, is_correct=is_correct)
        db.session.add(log)
    db.session.commit()

    # Adjust difficulty
    current_difficulty = adjust_difficulty(current_difficulty, correct_count, max(1, len(valid_answers)))
    session["current_difficulty"] = current_difficulty

    # Next round: fetch unseen questions strictly by subcategory
    all_questions = Question.query.filter_by(
        subcategory=subcategory,
        difficulty=current_difficulty
    ).all()
    unseen = [q for q in all_questions if not has_seen_question(session_id, q.id)]
    next_questions = random.sample(unseen, min(5, len(unseen)))

    for q in next_questions:
        mark_question_seen(session_id, q.id)

    return jsonify({
        "next_difficulty": current_difficulty,
        "questions": format_questions(next_questions)
    })

# --------------------
# Bootstrap
# --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)