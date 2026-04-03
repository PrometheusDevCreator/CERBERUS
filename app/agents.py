import httpx
from typing import List, Dict
import asyncio
import os
from pathlib import Path
from app.config import settings


# ── Load context files at startup ──
def _load_context_file(filename: str) -> str:
    """Load a context file from the context/ directory."""
    candidates = [
        Path(__file__).parent.parent / "context" / filename,
        Path("/app/context") / filename,
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


# Load baseline identity + shared project status
_sarah_baseline = _load_context_file("SARAH_BASELINE.md")
_claude_baseline = _load_context_file("CLAUDE_BASELINE.md")
_status = _load_context_file("STATUS.md")


def _build_system_prompt(baseline: str, fallback: str) -> str:
    """Combine baseline identity with current project status."""
    parts = []
    if baseline:
        parts.append(baseline)
    else:
        parts.append(fallback)

    if _status:
        parts.append("---\n\n# Current Project Status\n\n" + _status)

    return "\n\n".join(parts)


SARAH_SYSTEM_PROMPT = _build_system_prompt(
    _sarah_baseline,
    "You are Sarah, an AI agent in the CERBERUS triadic coordination system. "
    "You work alongside Claude and a human operator (Matthew). Be direct and collaborative."
)

CLAUDE_SYSTEM_PROMPT = _build_system_prompt(
    _claude_baseline,
    "You are Claude, an AI agent in the CERBERUS triadic coordination system. "
    "You work alongside Sarah and a human operator (Matthew). Be direct and collaborative."
)


async def call_sarah(message: str, conversation_history: List[Dict]) -> str:
    """Call OpenAI's GPT-5.4 (Sarah) with conversation history."""
    try:
        # conversation_history already includes the current message
        messages = conversation_history.copy()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.SARAH_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": SARAH_SYSTEM_PROMPT,
                        }
                    ]
                    + messages,
                    "max_completion_tokens": 4096,
                },
            )

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error: Unexpected response structure from OpenAI: {data}"

    except asyncio.TimeoutError:
        return "Error: Request to Sarah (OpenAI) timed out"
    except httpx.HTTPError as e:
        return f"Error: HTTP error calling Sarah: {str(e)}"
    except Exception as e:
        return f"Error: Unexpected error calling Sarah: {str(e)}"


async def call_claude(message: str, conversation_history: List[Dict]) -> str:
    """Call Anthropic's Claude Opus 4.6 with conversation history."""
    try:
        # conversation_history already includes the current message
        messages = conversation_history.copy()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.CLAUDE_MODEL,
                    "max_tokens": 4096,
                    "system": CLAUDE_SYSTEM_PROMPT,
                    "messages": messages,
                },
            )

            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                content = data["content"][0]
                if "type" in content and content["type"] == "text":
                    return content["text"]
                else:
                    return f"Error: Unexpected content type: {content.get('type')}"
            else:
                return f"Error: Unexpected response structure from Anthropic: {data}"

    except asyncio.TimeoutError:
        return "Error: Request to Claude (Anthropic) timed out"
    except httpx.HTTPError as e:
        return f"Error: HTTP error calling Claude: {str(e)}"
    except Exception as e:
        return f"Error: Unexpected error calling Claude: {str(e)}"
