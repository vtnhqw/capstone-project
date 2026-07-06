import math
from typing import Dict, Any, List
from backend.database import load_encrypted_notes, save_encrypted_notes, load_progress, save_progress

class MCPServer:
    """
    Model Context Protocol (MCP) Server for EduMind.
    Exposes system-level tools to the AI agents through a standard JSON-RPC schema.
    """
    
    def __init__(self):
        self.tools = {
            "check_academic_guidelines": {
                "name": "check_academic_guidelines",
                "description": "Cross-references a topic with syllabus standards and curriculum benchmarks.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "The educational topic (e.g. Calculus Derivatives)."},
                        "education_level": {"type": "string", "description": "Grade level, e.g. HighSchool, Undergraduate."}
                    },
                    "required": ["topic"]
                }
            },
            "get_educational_resources": {
                "name": "get_educational_resources",
                "description": "Searches for high-quality open-source references, online readings, or video channels.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "The topic name."}
                    },
                    "required": ["topic"]
                }
            },
            "calculate_spaced_repetition": {
                "name": "calculate_spaced_repetition",
                "description": "Applies the SM-2 algorithm to compute the optimal next review interval based on recall quality (0-5).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "recall_quality": {"type": "integer", "description": "User score from 0 (forgot) to 5 (perfect recall)."},
                        "previous_interval": {"type": "integer", "description": "Previous interval in days. Default is 0."},
                        "repetitions": {"type": "integer", "description": "Number of consecutive successful repetitions. Default is 0."},
                        "easiness_factor": {"type": "number", "description": "The SM-2 EF value. Default is 2.5."}
                    },
                    "required": ["recall_quality"]
                }
            },
            "secure_save_note": {
                "name": "secure_save_note",
                "description": "Encrypts and saves a study note. Requires the current session password.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "The note title."},
                        "content": {"type": "string", "description": "The note content to encrypt."},
                        "password": {"type": "string", "description": "User password to derive encryption key."}
                    },
                    "required": ["title", "content", "password"]
                }
            }
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available tools in MCP format."""
        return list(self.tools.values())

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Routes the execution to the corresponding local tool function."""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}
            
        try:
            if name == "check_academic_guidelines":
                return self._check_academic_guidelines(
                    arguments.get("topic"), 
                    arguments.get("education_level", "Undergraduate")
                )
            elif name == "get_educational_resources":
                return self._get_educational_resources(arguments.get("topic"))
            elif name == "calculate_spaced_repetition":
                return self._calculate_spaced_repetition(
                    int(arguments.get("recall_quality")),
                    int(arguments.get("previous_interval", 0)),
                    int(arguments.get("repetitions", 0)),
                    float(arguments.get("easiness_factor", 2.5))
                )
            elif name == "secure_save_note":
                return self._secure_save_note(
                    arguments.get("title"),
                    arguments.get("content"),
                    arguments.get("password")
                )
        except Exception as e:
            return {"error": f"Failed to execute tool '{name}': {str(e)}"}

    # Tool Implementations
    def _check_academic_guidelines(self, topic: str, education_level: str) -> Dict[str, Any]:
        # Mock academic curriculum validator database
        guidelines = {
            "calculus": {
                "core_standards": ["Limits and continuity", "Derivatives by first principles", "Product, Quotient, Chain rules", "Definite and Indefinite Integrals"],
                "competencies": "Students must demonstrate how rates of change apply to optimization problems."
            },
            "history": {
                "core_standards": ["Primary vs Secondary Sources", "Timeline Analysis", "Causation of World War Conflicts", "Impact of industrialization"],
                "competencies": "Students must identify ideological bias in primary source texts."
            },
            "computer science": {
                "core_standards": ["Data structures (Arrays, Linked Lists, Graphs)", "Asymptotic notation (Big-O)", "Recursion & backtracking", "Search & sorting algorithms"],
                "competencies": "Students must design space-efficient algorithms and analyze temporal complexity."
            }
        }
        
        # Match topic keyword
        matched_key = None
        for key in guidelines.keys():
            if key in topic.lower():
                matched_key = key
                break
                
        if matched_key:
            res = guidelines[matched_key]
            return {
                "status": "success",
                "standards": res["core_standards"],
                "expected_competencies": res["competencies"],
                "education_level": education_level,
                "note": "Validated against standard collegiate curriculum."
            }
        else:
            return {
                "status": "partial_success",
                "standards": ["General Concept Comprehension", "Key Vocabulary terms", "Critical application of content"],
                "expected_competencies": f"Explain the principles and mechanisms of {topic}.",
                "education_level": education_level,
                "note": "Topic is niche; displaying generic academic benchmarks."
            }

    def _get_educational_resources(self, topic: str) -> Dict[str, Any]:
        # Mock index of vetted educational channels and resources
        resources = [
            {"title": "Khan Academy - General Learning Lectures", "url": "https://www.khanacademy.org"},
            {"title": "CrashCourse YouTube Channel - Core Curriculum", "url": "https://www.youtube.com/user/crashcourse"},
            {"title": "MIT OpenCourseWare - Advanced Material", "url": "https://ocw.mit.edu"}
        ]
        
        if "calc" in topic.lower():
            resources.insert(0, {"title": "3Blue1Brown - Essence of Calculus", "url": "https://www.3blue1brown.com/lessons/essence-of-calculus"})
        elif "cs" in topic.lower() or "programming" in topic.lower() or "python" in topic.lower():
            resources.insert(0, {"title": "freeCodeCamp - Interactive Coding Tutorials", "url": "https://www.freecodecamp.org"})
            
        return {
            "topic": topic,
            "recommended_resources": resources,
            "tip": "Review these resources before taking the adaptive quiz master challenge."
        }

    def _calculate_spaced_repetition(self, q: int, interval: int, repetitions: int, ef: float) -> Dict[str, Any]:
        """
        Implementation of the SM-2 algorithm:
        q: recall quality (0-5)
        interval: previous interval in days
        repetitions: consecutive successful reviews
        ef: easiness factor
        """
        if q >= 3:
            if repetitions == 0:
                new_interval = 1
            elif repetitions == 1:
                new_interval = 6
            else:
                new_interval = math.ceil(interval * ef)
            new_repetitions = repetitions + 1
        else:
            new_interval = 1
            new_repetitions = 0
            
        # Calculate new Easiness Factor (EF)
        new_ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        if new_ef < 1.3:
            new_ef = 1.3
            
        return {
            "next_interval_days": new_interval,
            "repetitions": new_repetitions,
            "easiness_factor": round(new_ef, 3),
            "recommendation": "Review tomorrow" if new_interval == 1 else f"Review in {new_interval} days"
        }

    def _secure_save_note(self, title: str, content: str, password: str) -> Dict[str, Any]:
        notes = load_encrypted_notes(password)
        
        # Check if note already exists
        exists = False
        for note in notes:
            if note["title"] == title:
                note["content"] = content
                exists = True
                break
                
        if not exists:
            notes.append({"title": title, "content": content})
            
        save_encrypted_notes(notes, password)
        return {
            "status": "success",
            "message": f"Note '{title}' encrypted and safely committed to vault.",
            "total_secure_notes": len(notes)
        }
