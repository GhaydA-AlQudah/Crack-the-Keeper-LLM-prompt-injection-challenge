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
#   "gemini-3.1-flash-lite",
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


def load_tool_description(level: int) -> str:
    path = GAME_DIR / f"level{level}" / "tool_description.txt"

    with open(path, encoding="utf-8") as file:
        return file.read().strip()


def load_tool_text(level: int) -> str:
    path = GAME_DIR / f"level{level}" / "tool_text.txt"

    with open(path, encoding="utf-8") as file:
        return file.read().strip()


# ==================================================
# TOOL CONTEXT
# ==================================================

@dataclass
class LevelContext:
    tool_text: str
    on_tool_called: Optional[Callable[[], None]] = None


# ==================================================
# CREATE AGENT
# ==================================================

def get_agent(level: int) -> Agent:
    config = load_config(level)
    system_prompt = load_prompt(level)
    tool_desc = load_tool_description(level)

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
    def get_level_secret(ctx: RunContext[LevelContext]) -> str:
        """Return the text configured for the current level."""
        logger.info("Level tool called")
        if ctx.deps.on_tool_called:
            ctx.deps.on_tool_called()
        return ctx.deps.tool_text

    logger.info(f"Agent initialized for level {level}")

    return agent


# ==================================================
# INITIALIZE ALL 3 AGENTS AT STARTUP
# ==================================================

game_agents = {
    level: get_agent(level)
    for level in (1, 2, 3)
}


# Load tool texts once at startup
tool_texts = {
    level: load_tool_text(level)
    for level in (1, 2, 3)
}


# ==================================================
# SECRET
# Single source of truth = tool_text.txt
# ==================================================

def extract_flag(level: int) -> str:
    """The whole content of tool_text.txt is the secret."""
    return tool_texts[level].strip()



# ==================================================
# RUN AGENT FOR CURRENT LEVEL
# ==================================================

async def run_level_agent(
    level: int,
    message: str,
    history: list | None = None,
    on_tool_called: Optional[Callable[[], None]] = None,
):
    """Run the level agent and return (reply, updated_history, token_stats)."""

    if level not in game_agents:
        raise ValueError("Invalid level")

    current_history = history or []
    start_time = time.perf_counter()

    result = await game_agents[level].run(
        message,
        deps=LevelContext(
            tool_text=tool_texts[level],
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
        f"{result.output}\n"
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

    return result.output, result.all_messages(), token_stats