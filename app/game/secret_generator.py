import secrets
from logger import logger


def generate_session_secrets() -> dict[int, str]:
    """Generate fresh tool secrets for all 3 levels for one session."""
    session_secrets = {
        1: secrets.token_urlsafe(24),
        2: secrets.token_urlsafe(24),
        3: secrets.token_urlsafe(24),
    }

    logger.warning(
        "[SECRET GENERATOR] Generated session secrets | "
        f"Level 1: {session_secrets[1]} | "
        f"Level 2: {session_secrets[2]} | "
        f"Level 3: {session_secrets[3]}"
    )

    return session_secrets