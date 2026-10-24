import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.llm import run_level_agent, extract_flag
from app.game.secret_generator import generate_session_secrets

app = FastAPI(title="Crack the Robot")

MAX_ATTEMPTS = 5
MAX_MESSAGES = 15
MAX_TOKENS_LIMIT = 1000

# In-memory sessions (no database)
sessions = {}


def normalize(s: str) -> str:
    """Remove direction marks, whitespace and formatting characters, then uppercase."""
    return re.sub(r"[\u200e\u200f\u202a-\u202e\s`*\"']", "", s).upper()


def load_level_secret(level: int) -> str:
    """Load the submission secret for the specified level."""
    secret_path = (
        Path(__file__).resolve().parent
        / "game"
        / f"level{level}"
        / "level_secret.txt"
    )

    return secret_path.read_text(encoding="utf-8").strip()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SecretRequest(BaseModel):
    session_id: str
    secret: str


@app.post("/game/start")
def start_game():
    session_id = str(uuid.uuid4())

    # Generate fresh tool secrets for all levels for this session.
    session_secrets = generate_session_secrets()

    sessions[session_id] = {
        "current_level": 1,
        "attempts_left": MAX_ATTEMPTS,
        "messages_left": MAX_MESSAGES,
        "tokens_left": MAX_TOKENS_LIMIT,
        "completed": False,
        "history": [],
        "tool_called": False,
        "authorization": False,
        "messages_sent": 0,
        "secrets": session_secrets,
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

    input_tokens = max(1, len(req.message.strip()) // 4)

    if session["tokens_left"] < input_tokens:
        raise HTTPException(
            status_code=400,
            detail="Token limit reached for this level.",
        )

    session["messages_left"] -= 1
    session["tokens_left"] -= input_tokens
    session["messages_sent"] += 1

    level = session["current_level"]

    try:
        reply, session["history"], _ = await run_level_agent(
            level=level,
            message=req.message,
            history=session["history"],
            on_tool_called=lambda authorization: session.update({
                "tool_called": True,
                "authorization": authorization,
            }),
            session_secrets=session["secrets"],
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

    level = session["current_level"]

    # Levels 1 and 2 require an actual tool call and authorization=True.
    if level in (1, 2):
        if not session.get("tool_called", False):
            raise HTTPException(
                status_code=400,
                detail="The robot has not executed the tool yet.",
            )

        if session.get("authorization") is not True:
            raise HTTPException(
                status_code=400,
                detail="The tool has not been authorized.",
            )

    # Level 3 still requires at least 3 messages.
    if level == 3 and session["messages_sent"] < 3:
        raise HTTPException(
            status_code=400,
            detail="You must send at least 3 messages to the robot before submitting the secret.",
        )

    if session["attempts_left"] <= 0:
        raise HTTPException(
            status_code=403,
            detail="No attempts left",
        )

    if level in (1, 2):
        correct_secret = extract_flag(
            level,
            session["secrets"],
        )
        is_correct = normalize(req.secret) == normalize(correct_secret)

    else:
        # Level 3 accepts either its generated tool secret or "No".
        generated_secret = extract_flag(
            3,
            session["secrets"],
        )
        fixed_secret = load_level_secret(3)

        is_correct = (
            normalize(req.secret) == normalize(generated_secret)
            or normalize(req.secret) == normalize(fixed_secret)
        )

    if is_correct:
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
        session["authorization"] = False
        session["messages_sent"] = 0

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