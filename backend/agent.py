import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple
from backend.security import redact_pii
from backend.mcp_server import MCPServer
from backend.database import load_roadmap, save_roadmap, load_quizzes, save_quizzes

mcp = MCPServer()

class EduMindAgentGraph:
    """
    Orchestrates the Multi-Agent Study workflow graph.
    Demonstrates graph-based routing, MCP tool integration, and PII redaction.
    
    Graph Nodes:
      1. PII_Sanitizer_Node: Cleans student notes/syllabus.
      2. Coordinator_Agent_Node: Decides the execution route.
      3. Syllabus_Planner_Agent_Node: Processes inputs to construct a weekly Roadmap.
      4. Quiz_Master_Agent_Node: Generates tailored adaptive quizzes.
      5. Coach_Agent_Node: Evaluates user performance and runs spaced repetition.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def _call_gemini_api(self, prompt: str, system_instruction: str = None) -> str:
        """Helper to invoke Gemini API over direct HTTP requests."""
        if not self.api_key:
            raise ValueError("No Gemini API key provided.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        
        contents = {"parts": [{"text": prompt}]}
        if system_instruction:
            contents["role"] = "user" # in simple config, we can supply it in user content or use systemInstruction field
            
        data = {
            "contents": [contents],
        }
        
        if system_instruction:
            data["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                return res_body["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise Exception(f"Gemini API HTTP Error: {err_msg}")
        except Exception as e:
            raise Exception(f"Gemini API connection error: {str(e)}")

    def run_syllabus_planner(self, raw_input: str) -> Dict[str, Any]:
        """
        Agent Node: Syllabus Planner
        1. Sanitize input using PII node.
        2. Call MCP to check academic guidelines.
        3. Orchestrate study roadmap (via Live LLM or smart local fallback).
        """
        # Node 1: PII Sanitizer
        sanitized_input = redact_pii(raw_input)
        
        # Node 2: Coordinator decides topic keyword
        topic = "General Subject"
        if "calc" in sanitized_input.lower():
            topic = "Calculus"
        elif "c++" in sanitized_input.lower() or "cpp" in sanitized_input.lower() or "cplus" in sanitized_input.lower():
            topic = "C++ Programming"
        elif "hist" in sanitized_input.lower():
            topic = "History"
        elif "cs" in sanitized_input.lower() or "code" in sanitized_input.lower() or "python" in sanitized_input.lower():
            topic = "Computer Science"
            
        # Node 3: Call MCP Server guidelines check
        mcp_res = mcp.call_tool("check_academic_guidelines", {"topic": topic, "education_level": "Undergraduate"})
        standards = mcp_res.get("standards", [])
        competencies = mcp_res.get("expected_competencies", "")
        
        # Node 4: Content Generation
        if self.api_key:
            try:
                system_prompt = (
                    "You are the Syllabus Architect Agent. Create a structured 3-week study roadmap "
                    "with modules, topics, descriptions, and estimated study hours. Return ONLY a valid JSON object matching this schema: "
                    "{\"modules\": [{\"id\": 1, \"title\": \"...\", \"description\": \"...\", \"status\": \"not_started\", \"hours\": 2.5, \"topics\": [\"topic1\", \"topic2\"]}]}"
                )
                prompt = (
                    f"Create a study plan for: '{sanitized_input}'.\n"
                    f"Academic Standards to meet: {standards}\n"
                    f"Target Competencies: {competencies}"
                )
                llm_response = self._call_gemini_api(prompt, system_instruction=system_prompt)
                
                # Strip markdown syntax if LLM returns it
                clean_json = llm_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()
                
                roadmap_data = json.loads(clean_json)
                save_roadmap(roadmap_data)
                return {
                    "source": "live_gemini",
                    "roadmap": roadmap_data,
                    "pii_sanitized": sanitized_input != raw_input
                }
            except Exception as e:
                # Fall back to high-quality local generation if API fails
                pass
                
        # High Quality Rule-Based Fallback (Offline Mode)
        roadmap_data = self._generate_fallback_roadmap(topic, sanitized_input, standards)
        save_roadmap(roadmap_data)
        return {
            "source": "offline_simulation",
            "roadmap": roadmap_data,
            "pii_sanitized": sanitized_input != raw_input
        }

    def run_quizmaster(self, active_module_id: int) -> Dict[str, Any]:
        """
        Agent Node: Quizmaster
        1. Fetch current module.
        2. Generate active recall items (Live LLM or offline simulation).
        """
        roadmap = load_roadmap()
        target_module = None
        for m in roadmap.get("modules", []):
            if m["id"] == active_module_id:
                target_module = m
                break
                
        if not target_module:
            return {"error": "Module not found."}
            
        topics_str = ", ".join(target_module.get("topics", []))
        
        # Generation
        if self.api_key:
            try:
                system_prompt = (
                    "You are the Quizmaster Agent. Generate exactly 2 high-quality active recall questions "
                    "based on the provided topics. Return ONLY a valid JSON object matching this schema: "
                    "{\"flashcards\": [{\"id\": 1, \"module_id\": 1, \"question\": \"...\", \"answer\": \"...\", \"user_score\": 0.0, \"attempts\": 0}]}"
                )
                prompt = f"Create 2 flashcard questions for Module {active_module_id}: '{target_module['title']}' covering topics: {topics_str}."
                llm_response = self._call_gemini_api(prompt, system_instruction=system_prompt)
                
                clean_json = llm_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()
                
                quiz_data = json.loads(clean_json)
                
                # Merge into existing quizzes
                all_quizzes = load_quizzes()
                # filter out old flashcards for this module to replace them
                new_flashcards = [f for f in all_quizzes.get("flashcards", []) if f["module_id"] != active_module_id]
                
                # set correct module id and fresh IDs
                max_id = max([f["id"] for f in new_flashcards]) if new_flashcards else 0
                for i, card in enumerate(quiz_data.get("flashcards", [])):
                    card["module_id"] = active_module_id
                    card["id"] = max_id + i + 1
                    new_flashcards.append(card)
                    
                all_quizzes["flashcards"] = new_flashcards
                save_quizzes(all_quizzes)
                return {
                    "source": "live_gemini",
                    "flashcards": [f for f in new_flashcards if f["module_id"] == active_module_id]
                }
            except Exception:
                pass
                
        # Smart local offline generation
        all_quizzes = load_quizzes()
        new_flashcards = [f for f in all_quizzes.get("flashcards", []) if f["module_id"] != active_module_id]
        
        fallback_cards = self._generate_fallback_quiz(active_module_id, target_module["title"], target_module.get("topics", []))
        max_id = max([f["id"] for f in new_flashcards]) if new_flashcards else 0
        for i, card in enumerate(fallback_cards):
            card["id"] = max_id + i + 1
            new_flashcards.append(card)
            
        all_quizzes["flashcards"] = new_flashcards
        save_quizzes(all_quizzes)
        return {
            "source": "offline_simulation",
            "flashcards": fallback_cards
        }

    def run_study_coach(self, quiz_id: int, user_answer: str) -> Dict[str, Any]:
        """
        Agent Node: Study Coach
        1. Compares user's response with correct flashcard answer.
        2. Grades response from 0-5.
        3. Calls MCP server tool `calculate_spaced_repetition` to schedule next review.
        4. Updates progress.json metrics.
        """
        all_quizzes = load_quizzes()
        target_card = None
        for card in all_quizzes.get("flashcards", []):
            if card["id"] == quiz_id:
                target_card = card
                break
                
        if not target_card:
            return {"error": "Quiz item not found."}
            
        # Determine grading score (0-5)
        score = 3  # default
        justification = ""
        
        if self.api_key:
            try:
                system_prompt = (
                    "You are the Performance Study Coach Agent. Evaluate the student's answer against the target answer. "
                    "Rate the recall quality from 0 (completely wrong/empty) to 5 (excellent, fully accurate). "
                    "Format your response ONLY as JSON: {\"score\": 4, \"explanation\": \"...\"}"
                )
                prompt = (
                    f"Question: {target_card['question']}\n"
                    f"Reference Answer: {target_card['answer']}\n"
                    f"Student Answer: {user_answer}"
                )
                llm_response = self._call_gemini_api(prompt, system_instruction=system_prompt)
                
                clean_json = llm_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()
                
                grade_res = json.loads(clean_json)
                score = min(max(int(grade_res.get("score", 3)), 0), 5)
                justification = grade_res.get("explanation", "")
            except Exception:
                pass
                
        if not justification:
            # Simple keyword overlap grading for simulation fallback
            overlap = set(user_answer.lower().split()) & set(target_card["answer"].lower().split())
            ratio = len(overlap) / max(len(target_card["answer"].split()), 1)
            if ratio > 0.4:
                score = 5
                justification = "Excellent! You captured all key details of the definition."
            elif ratio > 0.2:
                score = 4
                justification = "Good effort. Most components of the concept are present."
            elif ratio > 0.05:
                score = 3
                justification = "Acceptable, but you missed some critical elements."
            else:
                score = 1
                justification = "Your response did not match the reference concept. Review recommended."
                
        # Call MCP Spaced Repetition Tool
        prev_interval = target_card.get("spaced_rep", {}).get("interval", 0) if "spaced_rep" in target_card else 0
        reps = target_card.get("spaced_rep", {}).get("repetitions", 0) if "spaced_rep" in target_card else 0
        ef = target_card.get("spaced_rep", {}).get("easiness_factor", 2.5) if "spaced_rep" in target_card else 2.5
        
        mcp_sched = mcp.call_tool("calculate_spaced_repetition", {
            "recall_quality": score,
            "previous_interval": prev_interval,
            "repetitions": reps,
            "easiness_factor": ef
        })
        
        # Update Card States
        target_card["spaced_rep"] = {
            "interval": mcp_sched.get("next_interval_days", 1),
            "repetitions": mcp_sched.get("repetitions", 0),
            "easiness_factor": mcp_sched.get("easiness_factor", 2.5)
        }
        target_card["user_score"] = float(score * 20) # convert to 0-100 scale
        target_card["attempts"] = target_card.get("attempts", 0) + 1
        save_quizzes(all_quizzes)
        
        # Update overall dashboard progress
        self._recalculate_aggregate_progress()
        
        return {
            "score_out_of_5": score,
            "explanation": justification,
            "spaced_repetition": mcp_sched.get("recommendation", "Review tomorrow"),
            "correct_answer": target_card["answer"]
        }

    def chat_tutor(self, message: str) -> Dict[str, Any]:
        """Provides direct conversational tutoring with memory and context."""
        sanitized_msg = redact_pii(message)
        
        if self.api_key:
            try:
                system_prompt = (
                    "You are EduMind's head tutor. You help students understand concepts, write explanations, "
                    "and plan study schedules. Keep your tone encouraging and professional. Do not list student's private grades unless requested."
                )
                llm_response = self._call_gemini_api(sanitized_msg, system_instruction=system_prompt)
                return {"reply": llm_response, "source": "live_gemini"}
            except Exception as e:
                return {"reply": f"Sorry, there was an issue running Gemini API: {str(e)}. I am defaulting to offline mode.", "source": "error"}
                
        # Smart simulated responses
        reply = "Hello! I am your EduMind study assistant operating in Local Offline Mode. "
        if "help" in sanitized_msg.lower():
            reply += "You can use this chat to ask about academic topics, generate study planners, or check study status."
        elif "hello" in sanitized_msg.lower() or "hi" in sanitized_msg.lower():
            reply += "Hi there! What subject are we studying today? Feel free to upload your syllabus or enter a topic above!"
        else:
            reply += f"I received your question about '{sanitized_msg}'. To get full active recall answers and details, connect your Gemini API key in the top right lock icon. For now, you can continue exploring the custom offline roadmaps, interactive flashcards, and the encrypted Lockbox!"
            
        return {"reply": reply, "source": "offline_simulation"}

    # Helper Generators (Simulations)
    def _generate_fallback_roadmap(self, topic: str, user_input: str, standards: List[str]) -> Dict[str, Any]:
        """Simulates structured roadmap generation for various subjects."""
        if topic == "Calculus":
            return {
                "modules": [
                    {
                        "id": 1,
                        "title": "Module 1: Limits and Continuity",
                        "description": "Master the definition of a limit, graphical limits, and algebraic evaluation.",
                        "status": "in_progress",
                        "hours": 3.0,
                        "topics": ["Graphical Limits", "Squeeze Theorem", "Continuity Definition"]
                    },
                    {
                        "id": 2,
                        "title": "Module 2: Rules of Differentiation",
                        "description": "Learn the Power, Product, Quotient, and Chain rules, and how to find derivatives.",
                        "status": "not_started",
                        "hours": 4.5,
                        "topics": ["Power Rule", "Chain Rule", "Implicit Differentiation"]
                    },
                    {
                        "id": 3,
                        "title": "Module 3: Applications of Derivatives",
                        "description": "Solve rates of change, velocity, acceleration, optimization, and curve sketching.",
                        "status": "not_started",
                        "hours": 5.0,
                        "topics": ["Optimization Problems", "Related Rates", "L'Hopital's Rule"]
                    }
                ]
            }
        elif topic == "C++ Programming":
            return {
                "modules": [
                    {
                        "id": 1,
                        "title": "Module 1: C++ Syntax & Control Flow",
                        "description": "Learn basic syntax, standard streams, primitive data types, scopes, and conditional loops.",
                        "status": "in_progress",
                        "hours": 3.5,
                        "topics": ["std::cout stream", "Main Function Structure", "Variables & Constants"]
                    },
                    {
                        "id": 2,
                        "title": "Module 2: Pointers & Memory Allocations",
                        "description": "Learn memory segments, dynamic heap allocation, pointer arithmetic, and reference types.",
                        "status": "not_started",
                        "hours": 5.0,
                        "topics": ["Stack vs Heap Allocation", "Pointer Dereferencing", "Memory Leaks & Smart Pointers"]
                    },
                    {
                        "id": 3,
                        "title": "Module 3: Object-Oriented C++ Programming",
                        "description": "Understand C++ classes, accessibility scopes, virtual functions, polymorphism, and memory destruction.",
                        "status": "not_started",
                        "hours": 6.0,
                        "topics": ["Virtual Destructors", "Method Overriding", "Access specifiers (public/private)"]
                    }
                ]
            }
        elif topic == "Computer Science":
            return {
                "modules": [
                    {
                        "id": 1,
                        "title": "Module 1: Basic Data Structures",
                        "description": "Understand Arrays, Linked Lists, Stack, and Queue abstract data types.",
                        "status": "in_progress",
                        "hours": 3.5,
                        "topics": ["Dynamic Arrays", "Singly Linked Lists", "Stack LIFO Operations"]
                    },
                    {
                        "id": 2,
                        "title": "Module 2: Analysis of Algorithms",
                        "description": "Explore Big-O, Big-Theta notation, and measure execution speed and space constraints.",
                        "status": "not_started",
                        "hours": 4.0,
                        "topics": ["Worst-case Complexity", "Space Complexity", "Recursive Call Stack"]
                    },
                    {
                        "id": 3,
                        "title": "Module 3: Non-Linear Structures",
                        "description": "Introduction to Binary Search Trees, Graphs, Breadth-First and Depth-First traversal.",
                        "status": "not_started",
                        "hours": 6.0,
                        "topics": ["Binary Search Tree Insertion", "DFS vs BFS", "Graph Adjacency List"]
                    }
                ]
            }
        elif topic == "History":
            return {
                "modules": [
                    {
                        "id": 1,
                        "title": "Module 1: Causes of the Great War",
                        "description": "Analyze primary texts, Alliance networks, militarism, and imperialism in Europe.",
                        "status": "in_progress",
                        "hours": 2.5,
                        "topics": ["Triple Entente vs Triple Alliance", "Balkan Crisis", "Assassination at Sarajevo"]
                    },
                    {
                        "id": 2,
                        "title": "Module 2: The Interwar Period",
                        "description": "Trace the Treaty of Versailles, the Great Depression, and the rise of totalitarian regimes.",
                        "status": "not_started",
                        "hours": 3.5,
                        "topics": ["League of Nations", "Weimar Hyperinflation", "Rise of Extremism"]
                    },
                    {
                        "id": 3,
                        "title": "Module 3: World War II Aftermath",
                        "description": "Analyze the geopolitical shifts, formation of the UN, and start of the Cold War.",
                        "status": "not_started",
                        "hours": 4.0,
                        "topics": ["Yalta & Potsdam Conferences", "United Nations Charter", "Iron Curtain Speech"]
                    }
                ]
            }
        else:
            # Dynamic generation based on keyword parsing
            words = [w for w in user_input.split() if len(w) > 3][:3]
            subject = " ".join(words) if words else "Custom Topic"
            return {
                "modules": [
                    {
                        "id": 1,
                        "title": f"Module 1: Foundational {subject}",
                        "description": f"Introduction to primary concepts and theoretical frameworks of {subject}.",
                        "status": "in_progress",
                        "hours": 3.0,
                        "topics": [f"Basic Principles of {subject}", "Historical Context"]
                    },
                    {
                        "id": 2,
                        "title": f"Module 2: Core Methodologies in {subject}",
                        "description": "Analysis of current methods, formulas, and tools used.",
                        "status": "not_started",
                        "hours": 4.0,
                        "topics": ["Key Methods", "Common Pitfalls"]
                    },
                    {
                        "id": 3,
                        "title": f"Module 3: Advanced Applications",
                        "description": "Synthesize the course materials and execute a case study or capstone.",
                        "status": "not_started",
                        "hours": 5.0,
                        "topics": ["Case Study Review", "Practical Exercises"]
                    }
                ]
            }

    def _generate_fallback_quiz(self, module_id: int, module_title: str, topics: List[str]) -> List[Dict[str, Any]]:
        """Simulates question creation matching the subject topic list."""
        if "Limits" in module_title or "Calculus" in module_title:
            return [
                {
                    "module_id": module_id,
                    "question": "Evaluate the limit of (x^2 - 1)/(x - 1) as x approaches 1.",
                    "answer": "The limit is 2. Factory the numerator to (x-1)(x+1), cancel out the (x-1) term, leaving limit of (x+1) as x approaches 1, which equals 1+1=2."
                },
                {
                    "module_id": module_id,
                    "question": "What does it mean for a function to be continuous at a point c?",
                    "answer": "A function is continuous at c if the limit as x approaches c exists, the function value f(c) is defined, and the limit equals f(c)."
                }
            ]
        elif "C++" in module_title or "Pointers" in module_title or "Syntax" in module_title or "Object-Oriented" in module_title:
            if module_id == 1:
                return [
                    {
                        "module_id": module_id,
                        "question": "What is the difference between a pointer and a reference in C++?",
                        "answer": "A pointer stores a memory address and can be re-assigned or null. A reference acts as an alias to an existing object, cannot be null, and cannot be re-assigned."
                    },
                    {
                        "module_id": module_id,
                        "question": "Why does every C++ console program require a 'main' function?",
                        "answer": "The 'main' function is the entry point of execution for C++ compilation where runtime starts and returns an integer status code to the OS."
                    }
                ]
            elif module_id == 2:
                return [
                    {
                        "module_id": module_id,
                        "question": "Explain stack vs heap memory allocation in C++.",
                        "answer": "Stack is managed automatically, faster, but limited in size. Heap is dynamic, manual (using new/delete or smart pointers), larger, but slower and prone to memory leaks."
                    },
                    {
                        "module_id": module_id,
                        "question": "What is a smart pointer in modern C++?",
                        "answer": "A smart pointer is a wrapper class like std::unique_ptr or std::shared_ptr that automatically manages heap allocation lifetimes using RAII."
                    }
                ]
            else:
                return [
                    {
                        "module_id": module_id,
                        "question": "What is a virtual destructor and why should classes with virtual methods use them?",
                        "answer": "A virtual destructor ensures that when a derived class is deleted through a base class pointer, the derived destructor is invoked, preventing resource leaks."
                    },
                    {
                        "module_id": module_id,
                        "question": "Explain dynamic polymorphism in C++.",
                        "answer": "It is runtime function binding implemented using virtual functions and pointers, allowing a base class interface to invoke derived class methods dynamically."
                    }
                ]
        elif "Data Structures" in module_title or "Computer" in module_title:
            return [
                {
                    "module_id": module_id,
                    "question": "What is the worst-case time complexity of inserting into a dynamic array?",
                    "answer": "The worst case is O(N) when the array is full and must be reallocated/copied to a new location. Average amortized time is O(1)."
                },
                {
                    "module_id": module_id,
                    "question": "Describe the main difference between a Stack and a Queue.",
                    "answer": "A Stack uses LIFO (Last In First Out) structure where elements are added and removed from the same end. A Queue uses FIFO (First In First Out) structure where elements are added at the back and removed from the front."
                }
            ]
        elif "Causes" in module_title or "History" in module_title:
            return [
                {
                    "module_id": module_id,
                    "question": "Which major nations formed the Triple Entente in 1907?",
                    "answer": "The Triple Entente was formed by Great Britain, France, and the Russian Empire."
                },
                {
                    "module_id": module_id,
                    "question": "What was the spark that ignited World War I in Europe?",
                    "answer": "The assassination of Archduke Franz Ferdinand of Austria and his wife Sophie in Sarajevo on June 28, 1914 by Bosnian Serb nationalist Gavrilo Princip."
                }
            ]
        else:
            topic_str = topics[0] if topics else "Subject material"
            return [
                {
                    "module_id": module_id,
                    "question": f"Explain the fundamental mechanism of {topic_str}.",
                    "answer": f"The fundamental mechanism of {topic_str} concerns the integration of theoretical structures with practical applications to yield predictable outcomes."
                },
                {
                    "module_id": module_id,
                    "question": f"State one common misconception regarding {topic_str}.",
                    "answer": f"A common misconception is that {topic_str} operates in isolation, when in fact it relies heavily on surrounding context and input parameters."
                }
            ]

    def _recalculate_aggregate_progress(self):
        """Helper to compute aggregate metrics across modules and quizzes."""
        from backend.database import load_progress, save_progress
        roadmap = load_roadmap()
        quizzes = load_quizzes()
        
        # Calculate modules progress
        modules = roadmap.get("modules", [])
        total_modules = len(modules)
        completed_modules = sum([1 for m in modules if m["status"] == "completed"])
        
        # Calculate study hours
        total_hours = sum([m["hours"] for m in modules if m["status"] == "completed" or m["status"] == "in_progress"])
        
        # Calculate average quiz scores
        cards = quizzes.get("flashcards", [])
        attempted_cards = [c for c in cards if c.get("attempts", 0) > 0]
        avg_score = 100.0
        if attempted_cards:
            avg_score = sum([c["user_score"] for c in attempted_cards]) / len(attempted_cards)
            
        # Discover weak areas (cards with score < 60)
        weak_areas = []
        for c in attempted_cards:
            if c["user_score"] < 60:
                # find module title
                mod_title = "General Module"
                for m in modules:
                    if m["id"] == c["module_id"]:
                        mod_title = m["title"]
                        break
                weak_areas.append(f"{mod_title}: Question on {c['question'][:25]}...")
                
        if not weak_areas:
            weak_areas = ["Looking strong! Keep up the review pace."]
            
        progress = {
            "total_hours": round(total_hours, 1),
            "completed_modules": completed_modules,
            "average_score": round(avg_score, 1),
            "weak_areas": weak_areas[:3] # keep top 3
        }
        save_progress(progress)
