import re
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.llm import run_level_agent, extract_flag

app = FastAPI(title="Crack the Robot")

MAX_ATTEMPTS = 5
MAX_MESSAGES = 15
MAX_TOKENS_LIMIT = 1000  # سقف التوكنز المتاح لكل جلسة/ليفل

# In-memory sessions (no database)
sessions = {}


def normalize(s: str) -> str:
    """Remove direction marks, whitespace and formatting characters, then uppercase."""
    return re.sub(r"[\u200e\u200f\u202a-\u202e\s`*\"']", "", s).upper()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SecretRequest(BaseModel):
    session_id: str
    secret: str


@app.post("/game/start")
def start_game():
    session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "current_level": 1,
        "attempts_left": MAX_ATTEMPTS,
        "messages_left": MAX_MESSAGES,
        "tokens_left": MAX_TOKENS_LIMIT,
        "completed": False,
        "history": [],
        "tool_called": False,
    }

    return {
        "session_id": session_id,
        "current_level": 1,
        "attempts_left": MAX_ATTEMPTS,
        "messages_left": MAX_MESSAGES,
        "tokens_left": MAX_TOKENS_LIMIT,
    }


@app.post("/game/chat")
async def chat(req: ChatRequest):
    session = sessions.get(req.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session["completed"]:
        raise HTTPException(
            status_code=400,
            detail="Game already completed",
        )

    if session["messages_left"] <= 0:
        raise HTTPException(
            status_code=400,
            detail="Message limit reached for this level.",
        )

    # حساب توكنز إدخال اليوزر بناءً على طول النص (حوالي كل 4 أحرف = 1 توكن تقريباً، أو الكلمات)
    input_tokens = max(1, len(req.message.strip()) // 4)

    if session["tokens_left"] < input_tokens:
        raise HTTPException(
            status_code=400,
            detail="Token limit reached for this level.",
        )

    # خصم الرسالة والتوكنز فوراً عند إرسالها من المستخدم
    session["messages_left"] -= 1
    session["tokens_left"] -= input_tokens

    level = session["current_level"]

    try:
        reply, session["history"], _ = await run_level_agent(
            level=level,
            message=req.message,
            history=session["history"],
            on_tool_called=lambda: session.update({"tool_called": True}),
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid level",
        )

    return {
        "level": level,
        "reply": reply,
        "messages_left": session["messages_left"],
        "tokens_left": session["tokens_left"],
    }


@app.post("/game/submit-secret")
def submit_secret(req: SecretRequest):
    session = sessions.get(req.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session["completed"]:
        raise HTTPException(
            status_code=400,
            detail="Game already completed",
        )

    if not session.get("tool_called", False):
        raise HTTPException(
            status_code=400,
            detail="The robot has not revealed the secret yet. You must force the robot to execute the tool first!",
        )

    if session["attempts_left"] <= 0:
        raise HTTPException(
            status_code=403,
            detail="No attempts left",
        )

    level = session["current_level"]

    if normalize(req.secret) == normalize(extract_flag(level)):

        if level == 3:
            session["completed"] = True

            return {
                "success": True,
                "completed": True,
                "message": "Challenge completed!",
            }

        session["current_level"] += 1
        session["attempts_left"] = MAX_ATTEMPTS
        session["messages_left"] = MAX_MESSAGES
        session["tokens_left"] = MAX_TOKENS_LIMIT
        session["history"] = []
        session["tool_called"] = False

        return {
            "success": True,
            "completed": False,
            "current_level": session["current_level"],
            "attempts_left": session["attempts_left"],
            "messages_left": session["messages_left"],
            "tokens_left": session["tokens_left"],
            "message": "Correct! Next level unlocked.",
        }

    session["attempts_left"] -= 1

    return {
        "success": False,
        "completed": False,
        "current_level": level,
        "attempts_left": session["attempts_left"],
        "messages_left": session["messages_left"],
        "tokens_left": session["tokens_left"],
        "message": "Incorrect secret.",
    }


@app.get("/health")
def health():
    return {"status": "ok"}