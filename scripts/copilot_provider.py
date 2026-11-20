"""Structured, tool-free Copilot SDK requests for the interactive workflow."""

import asyncio
import os
from pathlib import Path

MODEL = "gpt-6-luna"
TIMEOUT_SECONDS = 180


async def _request(instructions, prompt, schema):
    from copilot import CopilotClient, RuntimeConnection

    home = os.environ.get("COPILOT_HOME") or str(Path.home() / ".copilot")
    runtime = RuntimeConnection.for_default(base_directory=home)
    async with CopilotClient(mode="empty", runtime=runtime) as client:
        async with await client.create_session(
            model=MODEL,
            tools={"available_tools": []},
            system_message={"mode": "replace", "content": instructions},
            enable_config_discovery=False,
        ) as session:
            return await session.send_and_wait_typed(prompt, schema, timeout=TIMEOUT_SECONDS)


def request(instructions, prompt, schema):
    from find_categories import SetupError
    from pydantic import ValidationError

    try:
        from copilot import JsonRpcError
    except ImportError as e:
        raise SetupError("The Copilot SDK is not installed. Run: pip install -e .") from e
    try:
        result = asyncio.run(_request(instructions, prompt, schema))
    except (JsonRpcError, OSError, RuntimeError, TimeoutError, ValueError, ValidationError) as e:
        raise SetupError(f"Copilot request failed ({type(e).__name__}): {e}") from e
    except Exception as e:
        # Older SDK completion paths raise a plain Exception for session.error events.
        if type(e) is Exception and str(e).startswith("Session error:"):
            raise SetupError(f"Copilot request failed: {e}") from e
        raise
    if result is None:
        raise SetupError("Copilot returned no usable answer.")
    return result
