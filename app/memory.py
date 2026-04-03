import re
from typing import Iterable, List, Optional


MEMORY_CUES = (
    "remember",
    "keep in mind",
    "note that",
    "for future",
    "my preference is",
    "i prefer",
    "default to",
    "always",
    "never",
    "should default",
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_scope(text: str) -> str:
    lowered = text.lower()
    if "prometheus forge" in lowered or re.search(r"\bforge\b", lowered):
        return "forge"
    if any(token in lowered for token in ("cerberus", "sarah", "claude", "conference mode", "direct mode", "conference", "direct")):
        return "cerberus"
    return "global"


def categorize_memory(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("prefer", "default", "always", "never", "approval")):
        return "preference"
    if any(token in lowered for token in ("project", "repo", "deployment", "railway", "running")):
        return "project_state"
    return "fact"


def extract_memory_candidate(text: str, message_type: str) -> Optional[dict]:
    cleaned = normalize_whitespace(text)
    lowered = cleaned.lower()

    should_consider = message_type == "instruction" or any(cue in lowered for cue in MEMORY_CUES)
    if not should_consider:
        return None

    if len(cleaned) < 16:
        return None

    summary = cleaned
    for cue in MEMORY_CUES:
        pattern = rf"^.*?{re.escape(cue)}[:\s,-]*"
        stripped = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        if stripped != cleaned and stripped.strip():
            summary = stripped.strip()
            break

    if "." in summary:
        summary = summary.split(".", 1)[0].strip()

    summary = summary[:200].rstrip(" ,;:-")
    if len(summary) < 12:
        return None

    return {
        "scope": detect_scope(cleaned),
        "category": categorize_memory(cleaned),
        "summary": summary,
        "detail": cleaned,
        "tags": [],
    }


def rank_memories(memories: Iterable[dict], current_text: str, current_scope: str, limit: int = 5) -> List[dict]:
    current_tokens = set(re.findall(r"[a-z0-9_]+", current_text.lower()))

    scored = []
    for memory in memories:
        memory_text = f"{memory.get('summary', '')} {memory.get('detail', '')}".lower()
        memory_tokens = set(re.findall(r"[a-z0-9_]+", memory_text))
        overlap = len(current_tokens & memory_tokens)

        score = overlap
        if memory.get("scope") == current_scope:
            score += 4
        elif memory.get("scope") == "global":
            score += 2

        if memory.get("category") == "preference":
            score += 2

        updated_at = memory.get("updated_at") or memory.get("created_at") or ""
        scored.append((score, updated_at, memory))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [memory for _, _, memory in scored[:limit]]


def format_memory_context(memories: List[dict]) -> Optional[str]:
    if not memories:
        return None

    lines = ["[Persistent Memory]"]
    for memory in memories:
        category = memory.get("category", "fact").replace("_", " ")
        scope = memory.get("scope", "global")
        lines.append(f"- ({scope}/{category}) {memory.get('summary', '').strip()}")

    return "\n".join(lines)
