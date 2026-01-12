# DSAT-Prep-Website-Final
# SAT Mastery – Adaptive SAT Practice Platform

SAT Mastery is a full-stack adaptive SAT practice system that delivers
round-based, timed practice sessions with instant feedback and explanations.
The platform mirrors real SAT testing conditions while dynamically adjusting
difficulty based on student performance.

---

## 🚀 Features

### 📚 Subcategory-Based Practice
- Questions are selected strictly by SAT subcategory
- Subcategories align with College Board skill domains
- Ensures targeted practice (e.g., Linear Equations, Command of Evidence)

### 🔁 Round-Based Sessions
- Practice is organized into rounds
- Each round contains up to 5 questions
- Progress is tracked with a visible round counter

### ⏱️ Timed Practice
- Each round has a 5-minute countdown timer
- Timer auto-submits answers when time expires
- Simulates real SAT pacing

### 🧠 Adaptive Difficulty
- Difficulty automatically adjusts based on accuracy
- Correct performance increases difficulty
- Struggling performance reduces difficulty
- Difficulty is tracked per user session

### ✅ Instant Feedback & Explanations
- Shows correct/incorrect status after submission
- Displays correct answers when missed
- Provides full explanations stored in the database

### 🔄 No Repeated Questions
- Questions are tracked per session
- Already-seen questions are never repeated
- Ensures meaningful practice every round

---

## 🏗️ Tech Stack

### Frontend
- HTML, CSS, JavaScript
- Dynamic question rendering
- Timer and round tracking

### Backend
- Flask (Python)
- SQLAlchemy ORM
- SQLite database
- Session-based difficulty tracking

---

## 🔌 API Endpoints

### `POST /start`
Fetches unseen questions by subcategory and difficulty

**Request**
```json
{
  "subcategory": "Linear equations in one variable"
}
