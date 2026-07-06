import os
import json
from typing import Dict, Any, List
from backend.security import encrypt_data, decrypt_data

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db_data")
os.makedirs(DB_DIR, exist_ok=True)

ROADMAP_FILE = os.path.join(DB_DIR, "roadmap.json")
QUIZZES_FILE = os.path.join(DB_DIR, "quizzes.json")
PROGRESS_FILE = os.path.join(DB_DIR, "progress.json")
ENCRYPTED_NOTES_FILE = os.path.join(DB_DIR, "notes.enc")

# Default structure if files don't exist
DEFAULT_ROADMAP = {
    "modules": [
        {
            "id": 1,
            "title": "Welcome to EduMind",
            "description": "Get started by uploading your syllabus or typing a topic of interest.",
            "status": "completed", # "completed", "in_progress", "not_started"
            "hours": 0.5,
            "topics": ["Overview of System", "Privacy Protections"]
        },
        {
            "id": 2,
            "title": "Core Learning Concepts",
            "description": "Understand core learning theories: Active Recall and Spaced Repetition.",
            "status": "not_started",
            "hours": 0,
            "topics": ["Spaced Repetition Systems", "Active Recall Methods"]
        }
    ]
}

DEFAULT_QUIZZES = {
    "flashcards": [
        {
            "id": 1,
            "module_id": 1,
            "question": "What is Active Recall?",
            "answer": "Active Recall is a learning principle where you stimulate your memory during the learning process by testing yourself, rather than passively reading information.",
            "user_score": 0.0,
            "attempts": 0
        },
        {
            "id": 2,
            "module_id": 1,
            "question": "How does EduMind protect your privacy?",
            "answer": "EduMind redacts Academic PII (like emails, phone numbers, and names) and encrypts all learning logs locally using AES-256 before any data goes to LLM endpoints.",
            "user_score": 0.0,
            "attempts": 0
        }
    ]
}

DEFAULT_PROGRESS = {
    "total_hours": 0.5,
    "completed_modules": 1,
    "average_score": 100.0,
    "weak_areas": ["None yet! Keep studying."]
}

def load_json(filepath: str, default: Any) -> Any:
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump(default, f, indent=4)
        return default
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(filepath: str, data: Any):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

def load_roadmap() -> Dict[str, Any]:
    return load_json(ROADMAP_FILE, DEFAULT_ROADMAP)

def save_roadmap(data: Dict[str, Any]):
    save_json(ROADMAP_FILE, data)

def load_quizzes() -> Dict[str, Any]:
    return load_json(QUIZZES_FILE, DEFAULT_QUIZZES)

def save_quizzes(data: Dict[str, Any]):
    save_json(QUIZZES_FILE, data)

def load_progress() -> Dict[str, Any]:
    return load_json(PROGRESS_FILE, DEFAULT_PROGRESS)

def save_progress(data: Dict[str, Any]):
    save_json(PROGRESS_FILE, data)

# Secure Encrypted Notes Database
def save_encrypted_notes(notes: List[Dict[str, Any]], password: str):
    """Encrypt notes array and save to disk."""
    data_str = json.dumps(notes)
    encrypted_str = encrypt_data(data_str, password)
    with open(ENCRYPTED_NOTES_FILE, "w") as f:
        f.write(encrypted_str)

def load_encrypted_notes(password: str) -> List[Dict[str, Any]]:
    """Load, decrypt, and parse notes array from disk. Returns empty list on error/incorrect password."""
    if not os.path.exists(ENCRYPTED_NOTES_FILE):
        return []
    try:
        with open(ENCRYPTED_NOTES_FILE, "r") as f:
            encrypted_str = f.read()
        decrypted_str = decrypt_data(encrypted_str, password)
        return json.loads(decrypted_str)
    except Exception:
        # Return empty or raise error (representing bad password/unlocked status)
        return []
