import os
import json
from fastapi import FastAPI, HTTPException, Header, Body, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.agent import EduMindAgentGraph
from backend.database import load_roadmap, save_roadmap, load_quizzes, save_quizzes, load_progress, save_progress, load_encrypted_notes, save_encrypted_notes
from backend.security import encrypt_data, decrypt_data, redact_pii
from backend.mcp_server import MCPServer

app = FastAPI(title="EduMind - Privacy-First Study Concierge Backend")

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
mcp_server = MCPServer()

# Request schemas
class RoadmapRequest(BaseModel):
    syllabus_text: str
    api_key: Optional[str] = None

class QuizRequest(BaseModel):
    module_id: int
    api_key: Optional[str] = None

class AnswerRequest(BaseModel):
    quiz_id: int
    user_answer: str
    api_key: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    api_key: Optional[str] = None

class NoteRequest(BaseModel):
    title: str
    content: str
    password: str

class DecryptRequest(BaseModel):
    password: str

# Endpoints
@app.get("/api/progress")
async def get_progress():
    return load_progress()

@app.get("/api/roadmap")
async def get_roadmap():
    return load_roadmap()

@app.post("/api/roadmap")
async def create_roadmap(req: RoadmapRequest):
    agent = EduMindAgentGraph(api_key=req.api_key)
    res = agent.run_syllabus_planner(req.syllabus_text)
    return res

@app.post("/api/roadmap/complete/{module_id}")
async def complete_module(module_id: int):
    roadmap = load_roadmap()
    found = False
    for m in roadmap.get("modules", []):
        if m["id"] == module_id:
            m["status"] = "completed"
            m["hours"] = m.get("hours", 0) or 2.0  # assign default hours
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Module not found")
    save_roadmap(roadmap)
    
    # Recalculate progress
    agent = EduMindAgentGraph()
    agent._recalculate_aggregate_progress()
    return {"status": "success", "roadmap": roadmap}

@app.get("/api/quizzes")
async def get_all_quizzes():
    return load_quizzes()

@app.get("/api/quizzes/module/{module_id}")
async def get_module_quizzes(module_id: int, api_key: Optional[str] = None):
    agent = EduMindAgentGraph(api_key=api_key)
    res = agent.run_quizmaster(module_id)
    return res

@app.post("/api/quizzes/evaluate")
async def evaluate_answer(req: AnswerRequest):
    agent = EduMindAgentGraph(api_key=req.api_key)
    res = agent.run_study_coach(req.quiz_id, req.user_answer)
    return res

@app.post("/api/chat")
async def chat_tutor(req: ChatRequest):
    agent = EduMindAgentGraph(api_key=req.api_key)
    res = agent.chat_tutor(req.message)
    return res

# Encrypted Vault Endpoints
@app.post("/api/vault/verify")
async def verify_password(req: DecryptRequest):
    # Try to load notes. If decrypt fails, it returns empty list.
    # To check if password is correct, we can also check if we can open and if it doesn't throw.
    # If the file doesn't exist, password is valid by definition (new vault)
    notes = load_encrypted_notes(req.password)
    # Check if file exists. If it exists and load returns empty, it might be wrong password or genuinely empty.
    # We can write a dummy validator entry or just check return code.
    # To make it robust:
    notes_file = os.path.join(os.path.dirname(__file__), "..", "db_data", "notes.enc")
    if os.path.exists(notes_file):
        try:
            with open(notes_file, "r") as f:
                encrypted_str = f.read()
            decrypt_data(encrypted_str, req.password)
            return {"status": "success", "notes_count": len(notes)}
        except Exception:
            raise HTTPException(status_code=401, detail="Incorrect password. Vault remains locked.")
    else:
        # Create empty encrypted database if first time
        save_encrypted_notes([], req.password)
        return {"status": "success", "notes_count": 0, "message": "New secure vault created."}

@app.post("/api/vault/notes")
async def save_note(req: NoteRequest):
    # Verify password first
    try:
        notes = load_encrypted_notes(req.password)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid password credentials")
        
    res = mcp_server.call_tool("secure_save_note", {
        "title": req.title,
        "content": req.content,
        "password": req.password
    })
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.post("/api/vault/notes/load")
async def get_notes(req: DecryptRequest):
    # Try to load. If it raises error, return 401
    notes_file = os.path.join(os.path.dirname(__file__), "..", "db_data", "notes.enc")
    if os.path.exists(notes_file):
        try:
            with open(notes_file, "r") as f:
                enc = f.read()
            dec = decrypt_data(enc, req.password)
            return {"notes": json.loads(dec)}
        except Exception:
            raise HTTPException(status_code=401, detail="Incorrect password. Decryption failed.")
    return {"notes": []}

@app.post("/api/vault/notes/delete")
async def delete_note(title: str = Body(..., embed=True), password: str = Body(..., embed=True)):
    try:
        notes = load_encrypted_notes(password)
    except Exception:
        raise HTTPException(status_code=401, detail="Incorrect password")
        
    updated_notes = [n for n in notes if n["title"] != title]
    save_encrypted_notes(updated_notes, password)
    return {"status": "success", "message": f"Note '{title}' deleted from vault."}

# MCP Server Tool Explorer endpoints
@app.get("/api/tools")
async def list_tools():
    return mcp_server.list_tools()

@app.post("/api/tools/call")
async def call_tool(tool_name: str = Body(...), arguments: dict = Body(...)):
    res = mcp_server.call_tool(tool_name, arguments)
    return res

# Serve UI
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# Mount frontend directory for styles and scripts
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
else:
    print(f"Warning: Frontend directory not found at {FRONTEND_DIR}")
