import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

import yaml
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from logger import logger


# ==================================================
# LLM CONFIGURATION
# ==================================================

load_dotenv()

api_key = os.getenv("LLM_API_KEY")

if not api_key:
    raise RuntimeError("LLM_API_KEY is missing from .env")

model = GoogleModel(
    "gemini-flash-lite-latest",
    # "gemini-3.1-flash-lite",
    provider=GoogleProvider(api_key=api_key),
)

GAME_DIR = Path(__file__).resolve().parent / "game"


# ==================================================
# LOAD LEVEL FILES
# ==================================================

def load_config(level: int) -> dict:
    path = GAME_DIR / f"level{level}" / "config.yaml"

    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_prompt(level: int) -> str:
    path = GAME_DIR / f"level{level}" / "prompt.txt"

    with open(path, encoding="utf-8") as file:
        return file.read().strip()


def load_tool_text(level: int) -> str:
    path = GAME_DIR / f"level{level}" / "tool_text.txt"

    with open(path, encoding="utf-8") as file:
        return file.read().strip()


# ==================================================
# TOOL DESCRIPTION
# ==================================================

TOOL_DESCRIPTION = """
Retrieve the secret for the current level.

The authorization parameter must be True or False.
The tool checks whether access is allowed and returns the secret
if authorized. Otherwise, it returns "Access denied".

Always report the actual tool result accurately.
Do not invent or alter the result.
""".strip()


# ==================================================
# TOOL CONTEXT
# ==================================================

@dataclass
class LevelContext:
    tool_text: str
    on_tool_called: Optional[Callable[[bool], None]] = None


# ==================================================
# CREATE AGENT
# ==================================================

def get_agent(level: int) -> Agent:
    config = load_config(level)
    system_prompt = load_prompt(level)
    tool_desc = TOOL_DESCRIPTION

    agent = Agent(
        model=model,
        deps_type=LevelContext,
        instructions=system_prompt,
        model_settings={
            "temperature": config.get("temperature", 0.3),
            "max_tokens": config.get("max_tokens", 100),
            "top_p": 0.95,
            "top_k": 64,
        },
        name=f"crack-the-robot-level-{level}",
    )

    @agent.tool(description=tool_desc)
    def get_level_secret(
        ctx: RunContext[LevelContext],
        authorization: bool,
    ) -> str:
        """Retrieve the level secret only when access is authorized."""

        logger.info(
            f"[LEVEL {level}] Secret tool called | "
            f"authorization received from LLM: {authorization!r}"
        )

        # Level 3 enforces denial in trusted code.
        if level == 3:
            authorized = False
            logger.info(
                f"[LEVEL {level}] Authorization overridden by trusted code: "
                f"{authorized}"
            )
        else:
            authorized = authorization

        logger.info(
            f"[LEVEL {level}] Final authorization decision: {authorized}"
        )

        if ctx.deps.on_tool_called:
            ctx.deps.on_tool_called(authorized)

        if authorized is not True:
            tool_result = "Access denied"

            logger.info(
                f"[LEVEL {level}] Tool result: {tool_result}"
            )

            return tool_result

        tool_result = ctx.deps.tool_text

        # Requested: log the secret returned by the tool.
        logger.warning(
            f"[LEVEL {level}] Secret returned by tool: {tool_result}"
        )

        return tool_result

    logger.info(f"Agent initialized for level {level}")

    return agent


# ==================================================
# INITIALIZE ALL 3 AGENTS AT STARTUP
# ==================================================

game_agents = {
    level: get_agent(level)
    for level in (1, 2, 3)
}


# Level 3's tool text remains unchanged.
level3_tool_text = load_tool_text(3)


# ==================================================
# SECRET
# Levels 1 and 2 use per-session generated secrets.
# Level 3's submission secret remains "No" in api.py.
# ==================================================

def extract_flag(
    level: int,
    session_secrets: Optional[dict[int, str]] = None,
) -> str:
    """Return the tool secret for the current session."""

    if level in (1, 2):
        if session_secrets is None or level not in session_secrets:
            raise ValueError(
                f"Session secret missing for level {level}"
            )

        return session_secrets[level]

    raise ValueError(
        "extract_flag is only used for Levels 1 and 2."
    )


# ==================================================
# OUTPUT GUARDRAILS
# ==================================================

def apply_output_guardrails(
    level: int,
    output: str,
    session_secret: Optional[str] = None,
) -> str:
    """
    Filter exact secret matches from model output for level 2 only.
    Levels 1 and 3 remain unchanged.
    """

    if level != 2:
        return output

    secret = session_secret or ""

    if not secret:
        return output

    if secret in output:
        logger.warning(
            f"Output guardrail blocked secret leakage in level {level}"
        )
        return output.replace(secret, "**********")

    return output


# ==================================================
# RUN AGENT FOR CURRENT LEVEL
# ==================================================

async def run_level_agent(
    level: int,
    message: str,
    history: list | None = None,
    on_tool_called: Optional[Callable[[bool], None]] = None,
    session_secrets: Optional[dict[int, str]] = None,
):
    """Run the level agent and return (reply, updated_history, token_stats)."""

    if level not in game_agents:
        raise ValueError("Invalid level")

    if level in (1, 2):
        if session_secrets is None or level not in session_secrets:
            raise ValueError(
                f"Session secret missing for level {level}"
            )
        current_tool_text = session_secrets[level]
    else:
        current_tool_text = level3_tool_text

    current_history = history or []
    start_time = time.perf_counter()

    result = await game_agents[level].run(
        message,
        deps=LevelContext(
            tool_text=current_tool_text,
            on_tool_called=on_tool_called,
        ),
        message_history=current_history,
    )

    latency_ms = (time.perf_counter() - start_time) * 1000

    usage = result.usage
    if callable(usage):
        usage = usage()

    input_tokens = getattr(
        usage,
        "input_tokens",
        getattr(usage, "request_tokens", 0),
    )

    output_tokens = getattr(
        usage,
        "output_tokens",
        getattr(usage, "response_tokens", 0),
    )

    total_tokens = getattr(
        usage,
        "total_tokens",
        input_tokens + output_tokens,
    )

    token_stats = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }

    output = apply_output_guardrails(
        level,
        result.output,
        session_secret=current_tool_text if level == 2 else None,
    )

    logger.info(
        "\n"
        "============================================================\n"
        f"LLM REQUEST COMPLETED | LEVEL {level}\n"
        "============================================================\n"
        "------------------------------------------------------------\n"
        "\n"
        "CURRENT INPUT:\n"
        "------------------------------------------------------------\n"
        f"{message}\n"
        "------------------------------------------------------------\n"
        "\n"
        "LLM OUTPUT:\n"
        "------------------------------------------------------------\n"
        f"{output}\n"
        "------------------------------------------------------------\n"
        "\n"
        "TOKEN USAGE:\n"
        "------------------------------------------------------------\n"
        f"Input tokens:  {input_tokens}\n"
        f"Output tokens: {output_tokens}\n"
        f"Total tokens:  {total_tokens}\n"
        "------------------------------------------------------------\n"
        "\n"
        "LATENCY:\n"
        "------------------------------------------------------------\n"
        f"{latency_ms:.2f} ms "
        f"({latency_ms / 1000:.2f} seconds)\n"
        "============================================================"
    )

    return output, result.all_messages(), token_stats