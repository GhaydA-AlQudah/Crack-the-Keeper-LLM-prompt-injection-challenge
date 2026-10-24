
import secrets

from logger import logger


def generate_session_secrets() -> dict[int, str]:
    """Generate fresh tool secrets for Levels 1 and 2 for one session."""

    session_secrets = {
        1: secrets.token_urlsafe(24),
        2: secrets.token_urlsafe(24),
    }

    # Requested: log generated secrets for debugging.
    logger.warning(
        "[SECRET GENERATOR] Generated session secrets | "
        f"Level 1: {session_secrets[1]} | "
        f"Level 2: {session_secrets[2]}"
    )

    return session_secrets
