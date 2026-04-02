import httpx
from typing import List, Dict
import asyncio
from app.config import settings


async def call_sarah(message: str, conversation_history: List[Dict]) -> str:
    """Call OpenAI's GPT-5.4 (Sarah) with conversation history."""
    try:
        # Build messages list
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": message})

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
                            "content": "You are Sarah, an AI agent in the CERBERUS triadic coordination system. "
                            "You work alongside Claude and a human operator (Matthew) to solve complex problems. "
                            "Be clear, helpful, and collaborative.",
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
        # Build messages list
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": message})

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
                    "system": "You are Claude, an AI agent in the CERBERUS triadic coordination system. "
                    "You work alongside Sarah (an OpenAI model) and a human operator (Matthew) to solve complex problems. "
                    "Be clear, helpful, and collaborative.",
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
