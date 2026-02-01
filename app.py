from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask import redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import random
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------
# App Setup
# --------------------
app = Flask(__name__, static_folder="static")
app.secret_key = "dev-secret-key"

is_vercel = os.getenv("VERCEL") == "1"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/sat_practice.db" if is_vercel else "sqlite:///sat_practice.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

with app.app_context():
    db.create_all()


# --------------------
# In-Memory Session Store
# --------------------
SESSION_QUESTIONS_SEEN = {}

def get_or_create_session():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    SESSION_QUESTIONS_SEEN.setdefault(session["session_id"], set())
    return session["session_id"]

def mark_question_seen(session_id, question_id):
    SESSION_QUESTIONS_SEEN[session_id].add(question_id)

def has_seen_question(session_id, question_id):
    return question_id in SESSION_QUESTIONS_SEEN.get(session_id, set())

# --------------------
# Models
# --------------------
class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(20), nullable=False)
    subcategory = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False)
    stimulus = db.Column(db.Text)
    prompt = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(200), nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    answer_options = db.Column(db.Text)

class AnswerLog(db.Model):
    __tablename__ = "answer_logs"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False)
    question_id = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    current_difficulty = db.Column(db.Integer, default=2)
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --------------------
# Auth Helpers
# --------------------
def login_user(user):
    session["user_id"] = user.id

def logout_user():
    session.pop("user_id", None)

def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

def login_required():
    return current_user() is not None

def admin_required():
    user = current_user()
    return user is not None and user.is_admin

# --------------------
# Utility Functions
# --------------------
def adjust_difficulty(current, correct, total):
    accuracy = correct / total
    if accuracy >= 0.8:
        return min(current + 1, 3)
    if accuracy <= 0.4:
        return max(current - 1, 1)
    return current

def generate_ai_question(category, subcategory, difficulty):
    prompt = f"""
You are an SAT question writer. The SAT has two major categories which are English and Math. Each category has multiple subcategories. 

Generate ONE {category.upper()} SAT question.

Rules:
- Difficulty level: {difficulty} (1 easy, 2 medium, 3 hard)
- Subcategory: {subcategory}
- Multiple choice with 4 options (A–D)
- Correct answer MUST be a letter (A, B, C, or D)
- Include a clear explanation

Return ONLY valid JSON in this format:

{{
  "stimulus": "",
  "prompt": "question text",
  "choices": {{
    "A": "option text",
    "B": "option text",
    "C": "option text",
    "D": "option text"
  }},
  "correct_answer": "A",
  "explanation": "step-by-step explanation"
}}
"""
    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3 + random.random()*0.2,
        response_format={"type": "json_object"},
    )
    
    print(response.choices[0].message.content) 
    return json.loads(response.choices[0].message.content)


def format_questions(questions):
    formatted = []
    for q in questions:
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
@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/tips")
def tips():
    if not current_user():
        return app.send_static_file("login.html")
    return app.send_static_file("tips.html")

@app.route("/practice")
def practice():
    if not login_required():
        return app.send_static_file("login.html")
    return app.send_static_file("practice.html")
    

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return app.send_static_file("signup.html")

    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    user = User(name=name, email=email)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({"success": True})



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return app.send_static_file("login.html")

    data = request.get_json() or request.form
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return app.send_static_file("login.html")

    login_user(user)
    return redirect("/tips")

@app.route("/logout")
def logout():
    logout_user()
    return app.send_static_file("logout.html")

@app.route("/admin")
def admin():
    if not admin_required():
        return app.send_static_file("login.html")
    return app.send_static_file("admin.html")

@app.route("/admin/generate", methods=["POST"])
def admin_generate():
    if not admin_required():
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    category = data["category"]
    subcategory = data["subcategory"]
    difficulty = int(data["difficulty"])

    ai_data = generate_ai_question(category, subcategory, difficulty)

    question = Question(
        category=category,
        subcategory=subcategory,
        difficulty=difficulty,
        stimulus=ai_data.get("stimulus", ""),
        prompt=ai_data["prompt"],
        correct_answer=ai_data["correct_answer"],
        explanation=ai_data["explanation"],
        answer_options=json.dumps(ai_data["choices"])
    )

    db.session.add(question)
    db.session.commit()

    return jsonify({
        "success": True,
        "question_id": question.id,
        "preview": ai_data
    })


@app.route("/start", methods=["POST"])
def start():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    subcategory = data.get("subcategory")
    session_id = get_or_create_session()

    difficulty = user.current_difficulty

    all_questions = Question.query.filter_by(
        subcategory=subcategory,
        difficulty=difficulty
    ).all()

    unseen = [q for q in all_questions if not has_seen_question(session_id, q.id)]
    questions = random.sample(unseen, min(5, len(unseen)))

    for q in questions:
        mark_question_seen(session_id, q.id)

    return jsonify({
        "difficulty": difficulty,
        "questions": format_questions(questions)
    })

@app.route("/submit", methods=["POST"])
def submit():
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    subcategory = data.get("subcategory")
    answers = data.get("answers", [])

    session_id = get_or_create_session()
    correct_count = 0

    for a in answers:
        q_id = a.get("question_id")
        user_answer = str(a.get("user_answer"))
        correct_answer = str(a.get("correct_answer"))

        if not q_id:
            continue

        is_correct = user_answer == correct_answer
        correct_count += int(is_correct)

        db.session.add(
            AnswerLog(
                session_id=session_id,
                question_id=q_id,
                is_correct=is_correct
            )
        )

    db.session.commit()

    user.current_difficulty = adjust_difficulty(
        user.current_difficulty,
        correct_count,
        max(1, len(answers))
    )
    db.session.commit()

    all_questions = Question.query.filter_by(
        subcategory=subcategory,
        difficulty=user.current_difficulty
    ).all()

    unseen = [q for q in all_questions if not has_seen_question(session_id, q.id)]
    next_questions = random.sample(unseen, min(5, len(unseen)))

    for q in next_questions:
        mark_question_seen(session_id, q.id)

    return jsonify({
        "next_difficulty": user.current_difficulty,
        "questions": format_questions(next_questions)
    })

# --------------------
# Bootstrap
# --------------------
if __name__ == "__main__":
    app.run(debug=True)

