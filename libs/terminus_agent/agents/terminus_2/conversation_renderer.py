"""Render full_conversation.json messages into a readable Markdown file."""

from __future__ import annotations

import json
import re


def render_conversation_markdown(
    messages: list[dict],
    skill_log: dict | None = None,
) -> str:
    """Convert a list of chat messages into readable Markdown.

    Each message is expected to have ``role`` (user/assistant) and ``content`` keys.
    Assistant messages may be JSON strings with structured fields
    (analysis, plan, commands, task_complete) or skill-load requests.

    If *skill_log* is provided, a skill summary section is rendered at the top
    and skill-load events are annotated inline with metadata.
    """
    parts: list[str] = ["# Conversation Log\n"]

    if skill_log:
        parts.append(_render_skill_summary(skill_log))
        parts.append("")

    turn = 0

    for msg in messages:
        role = msg.get("role", "unknown")
        raw_content = msg.get("content", "")
        # Tool-capable providers can emit structured command entries with a
        # null content/keystrokes field.  Conversation rendering is diagnostic
        # only and must never turn an otherwise completed verifier run into an
        # infrastructure failure.
        content = "" if raw_content is None else str(raw_content)
        turn += 1

        parts.append(f"## Turn {turn} — {role.capitalize()}\n")

        if role == "assistant":
            parts.append(_render_assistant(content))
        elif role == "user":
            parts.append(_render_user(content, is_first=(turn == 1), skill_log=skill_log))
        else:
            parts.append(content + "\n")

        parts.append("")  # blank line between turns

    return "\n".join(parts)


def _render_skill_summary(skill_log: dict) -> str:
    """Render the skill summary header block."""
    lines: list[str] = ["## Skill Summary\n"]

    # Available skills
    available = skill_log.get("skills_available", [])
    if available:
        labels = []
        for s in available:
            source = s.get("source", "")
            label = f"`{s['name']}`"
            if source:
                label += f" ({source})"
            labels.append(label)
        lines.append(f"**Available** ({len(available)}): {', '.join(labels)}")
    else:
        lines.append("**Available**: none")

    # Injected
    injected = skill_log.get("skills_injected", [])
    if injected:
        lines.append(f"**Injected**: {', '.join(f'`{n}`' for n in injected)}")

    # Loaded by agent
    loaded = skill_log.get("skills_loaded", [])
    if loaded:
        lines.append(f"**Loaded by agent**: {', '.join(f'`{n}`' for n in loaded)}")

    # Not loaded
    not_loaded = skill_log.get("skills_not_loaded", [])
    if not_loaded:
        lines.append(f"**Not loaded**: {', '.join(f'`{n}`' for n in not_loaded)}")

    # Skill changes
    created = skill_log.get("skills_created", [])
    updated = skill_log.get("skills_updated", [])
    deprecated = skill_log.get("skills_deprecated", [])
    imported = skill_log.get("skills_imported", [])
    actions = skill_log.get("evolution_actions", [])

    has_changes = created or updated or deprecated or imported or actions
    if has_changes:
        lines.append("")
        lines.append("### Skill Changes This Run")
        # Prefer evolution_actions if available (has rationale)
        if actions:
            for a in actions:
                action_type = a.get("type", "UNKNOWN")
                skill_name = a.get("skill", "?")
                rationale = a.get("rationale", "")
                entry = f"- **{action_type}** `{skill_name}`"
                if rationale:
                    entry += f" — {rationale}"
                lines.append(entry)
        else:
            for s in created:
                desc = s.get("description", "")
                entry = f"- **CREATE** `{s['name']}`"
                if desc:
                    entry += f" — {desc}"
                lines.append(entry)
            for s in updated:
                entry = f"- **UPDATE** `{s['name']}` v{s.get('version_before', '?')} → v{s.get('version_after', '?')}"
                lines.append(entry)
            for s in deprecated:
                lines.append(f"- **DEPRECATE** `{s['name']}`")
        if imported:
            for s in imported:
                source = s.get("source_path", "")
                entry = f"- **IMPORT** `{s['name']}`"
                if source:
                    entry += f" (from {source})"
                lines.append(entry)

    # Verification result
    verification_source = skill_log.get("verification_source")
    tests_passed = skill_log.get("tests_passed")
    tests_failed = skill_log.get("tests_failed")
    test_details = skill_log.get("test_details")

    if verification_source or tests_passed is not None:
        lines.append("")
        lines.append("### Verification Result")
        total = (tests_passed or 0) + (tests_failed or 0)
        source_label = f"`{verification_source}`" if verification_source else "unknown"
        lines.append(f"Source: {source_label} — {tests_passed or 0}/{total} tests passed, {tests_failed or 0} failed")

        if test_details:
            for t in test_details:
                status = t.get("status", "UNKNOWN")
                name = t.get("name", "?")
                message = t.get("message", "")
                if status in ("PASSED", "passed"):
                    lines.append(f"- PASS `{name}`")
                else:
                    entry = f"- FAIL `{name}`"
                    if message:
                        entry += f" — {message}"
                    lines.append(entry)

    lines.append("")
    lines.append("---\n")
    return "\n".join(lines)


def _render_assistant(content: str) -> str:
    """Parse assistant JSON into labeled sections, or show raw text."""
    content = "" if content is None else str(content)
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content + "\n"

    if not isinstance(data, dict):
        return content + "\n"

    # Skill-load one-liner
    if "load_skill" in data:
        return f"> **Load skill:** `{data['load_skill']}`\n"

    sections: list[str] = []

    if data.get("analysis"):
        sections.append(f"**Analysis**\n\n{data['analysis']}\n")

    if data.get("plan"):
        sections.append(f"**Plan**\n\n{data['plan']}\n")

    if data.get("commands"):
        cmds = data["commands"]
        keystrokes = []
        for cmd in cmds:
            if isinstance(cmd, dict):
                ks = cmd.get("keystrokes", "")
                if ks is None:
                    ks = ""
                elif not isinstance(ks, str):
                    ks = str(ks)
                keystrokes.append(ks.rstrip("\n"))
            else:
                keystrokes.append(str(cmd))
        sections.append("**Commands**\n\n```bash\n" + "\n".join(keystrokes) + "\n```\n")

    if data.get("task_complete"):
        sections.append("> **Task complete**\n")

    if sections:
        return "\n".join(sections)

    # Unknown JSON structure — pretty-print it
    return "```json\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n```\n"


_TRUNCATION_LINES = 30


def _render_user(content: str, *, is_first: bool, skill_log: dict | None = None) -> str:
    """Render user messages: truncate the initial system prompt, show the rest."""
    content = "" if content is None else str(content)
    if is_first:
        return _render_first_user_message(content, skill_log=skill_log)

    # Check for skill-load responses
    stripped = content.strip()
    if stripped.startswith("Loaded skill: "):
        return _render_skill_load(stripped, skill_log=skill_log)
    if stripped.startswith("Skill not found: "):
        skill_name = stripped[len("Skill not found: ") :].strip()
        return f"> **Skill not found:** `{skill_name}`\n"

    # Subsequent user messages are mostly terminal output
    if stripped:
        return "```\n" + stripped + "\n```\n"
    return "*[empty]*\n"


def _render_first_user_message(content: str, *, skill_log: dict | None = None) -> str:
    """Render the first user message (system prompt) with skill extraction."""
    if not skill_log:
        # No skill_log — fall back to simple truncation
        lines = content.splitlines()
        if len(lines) > _TRUNCATION_LINES:
            tail = lines[-_TRUNCATION_LINES:]
            return f"*[System prompt truncated — showing last {_TRUNCATION_LINES} lines]*\n\n" + "```\n" + "\n".join(tail) + "\n```\n"
        return "```\n" + content + "\n```\n"

    parts: list[str] = []
    parts.append("*[System prompt truncated]*\n")

    # Show skills available to agent from skill_log
    available = skill_log.get("skills_available", [])
    if available:
        parts.append("**Skills available to agent:**")
        for s in available:
            source = s.get("source", "")
            desc = s.get("description", "")
            entry = f"- `{s['name']}`"
            extras = []
            if desc:
                extras.append(desc)
            if source:
                extras.append(source)
            if extras:
                entry += f" — {', '.join(extras)}"
            parts.append(entry)
        parts.append("")

    # Extract task description from content
    task_desc = _extract_task_description(content)
    if task_desc:
        parts.append("**Task:**")
        parts.append(f"> {task_desc}\n")

    return "\n".join(parts)


def _render_skill_load(content: str, *, skill_log: dict | None = None) -> str:
    """Render a skill-load response with collapsible content and metadata."""
    # Extract skill name from first line
    first_line_end = content.find("\n")
    if first_line_end == -1:
        first_line = content
        rest = ""
    else:
        first_line = content[:first_line_end]
        rest = content[first_line_end + 1 :]

    # Parse "Loaded skill: <name>" — may also have "---" separator
    name_match = re.match(r"Loaded skill:\s*(.+)", first_line)
    skill_name = name_match.group(1).strip() if name_match else "unknown"

    # Strip leading "---" separator from rest
    rest = rest.strip()
    if rest.startswith("---"):
        rest = rest[3:].strip()

    # Build metadata annotation from skill_log
    meta_parts: list[str] = []
    if skill_log:
        for s in skill_log.get("skills_available", []):
            if s.get("name") == skill_name:
                source = s.get("source", "")
                if source:
                    meta_parts.append(source)
                break

    meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""

    lines: list[str] = [f"> **Skill loaded: `{skill_name}`**{meta_str}\n"]

    if rest:
        lines.append("<details><summary>Skill content (click to expand)</summary>\n")
        lines.append("```")
        lines.append(rest)
        lines.append("```\n")
        lines.append("</details>\n")

    return "\n".join(lines)


def _extract_task_description(content: str) -> str:
    """Extract the task description from the system prompt content."""
    marker = "Task Description:\n"
    idx = content.find(marker)
    if idx == -1:
        return ""
    desc = content[idx + len(marker) :].strip()
    # Take first paragraph (up to double newline or 500 chars)
    end = desc.find("\n\n")
    if end != -1:
        desc = desc[:end]
    if len(desc) > 500:
        desc = desc[:500] + "..."
    return desc
