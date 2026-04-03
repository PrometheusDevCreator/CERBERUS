import httpx
from typing import List, Dict
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


# Load baseline identity + project portfolio
_sarah_baseline = _load_context_file("SARAH_BASELINE.md")
_claude_baseline = _load_context_file("CLAUDE_BASELINE.md")
_projects = _load_context_file("PROJECTS.md")


def _build_system_prompt(baseline: str, fallback: str) -> str:
    """Combine baseline identity with project awareness."""
    parts = []
    parts.append(baseline if baseline else fallback)

    if _projects:
        parts.append("---\n\n" + _projects)

    return "\n\n".join(parts)


SARAH_SYSTEM_PROMPT = _build_system_prompt(
    _sarah_baseline,
    "You are Sarah, an AI agent in CERBERUS. You work alongside Claude and Matthew. Be conversational and helpful."
)

CLAUDE_SYSTEM_PROMPT = _build_system_prompt(
    _claude_baseline,
    "You are Claude, an AI agent in CERBERUS. You work alongside Sarah and Matthew. Be conversational and helpful."
)


async def call_sarah(conversation_history: List[Dict]) -> str:
    """Call OpenAI's GPT-5.4 (Sarah) with conversation history."""
    try:
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
                        {"role": "system", "content": SARAH_SYSTEM_PROMPT}
                    ] + conversation_history,
                    "max_completion_tokens": 4096,
                },
            )
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error: Unexpected response from OpenAI: {data}"

    except httpx.TimeoutException:
        return "Error: Request to Sarah timed out"
    except httpx.HTTPStatusError as e:
        return f"Error calling Sarah: HTTP {e.response.status_code}"
    except httpx.HTTPError as e:
        return f"Error calling Sarah: {str(e)}"
    except Exception as e:
        return f"Error calling Sarah: {str(e)}"


async def call_claude(conversation_history: List[Dict]) -> str:
    """Call Anthropic's Claude Opus 4.6 with conversation history."""
    try:
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
                    "messages": conversation_history,
                },
            )
            response.raise_for_status()

            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                content = data["content"][0]
                if content.get("type") == "text":
                    return content["text"]
                else:
                    return f"Error: Unexpected content type: {content.get('type')}"
            else:
                return f"Error: Unexpected response from Anthropic: {data}"

    except httpx.TimeoutException:
        return "Error: Request to Claude timed out"
    except httpx.HTTPStatusError as e:
        return f"Error calling Claude: HTTP {e.response.status_code}"
    except httpx.HTTPError as e:
        return f"Error calling Claude: {str(e)}"
    except Exception as e:
        return f"Error calling Claude: {str(e)}"
