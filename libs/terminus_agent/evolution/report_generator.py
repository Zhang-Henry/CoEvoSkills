"""Generate a human-readable Markdown report from an evolution_run_log.json dict."""

from __future__ import annotations


def generate_evolution_report(log: dict) -> str:
    """Convert an evolution run log dict into a Markdown report string.

    Pure function: no side-effects, no class dependencies.
    """
    parts: list[str] = []

    task_name = log.get("task_name", "unknown")
    parts.append(f"# Evolution Report: {task_name}\n")

    # ── Meta info table ──
    parts.append(_section_meta(log))

    # ── Timing ──
    parts.append(_section_timing(log))

    # ── Intervention history ──
    parts.append(_section_intervention_history(log))

    # ── GT Oracle check ──
    parts.append(_section_oracle(log))

    # ── Token usage ──
    parts.append(_section_tokens(log))

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────
# Section builders
# ──────────────────────────────────────────────────────────────────


def _section_meta(log: dict) -> str:
    ts = _format_timestamp(log.get("timestamp", ""))

    rows = [
        ("Task", f"`{log.get('task_name', 'unknown')}`"),
        ("Model", f"`{log.get('model', '')}`"),
        ("Timestamp", ts),
    ]
    return _md_table(["Key", "Value"], rows) + "\n"


def _section_timing(log: dict) -> str:
    timing = log.get("timing", {})
    rows = [
        ("Skill Selection", _fmt_dur(timing.get("selection_duration_sec"))),
        ("Agent Execution", _fmt_dur(timing.get("execution_duration_sec"))),
        ("Evolution Loop", _fmt_dur(timing.get("evolution_duration_sec"))),
        ("**Total**", f"**{_fmt_dur(timing.get('total_duration_sec'))}**"),
    ]
    lines = ["## Timing\n"]
    lines.append(_md_table(["Phase", "Duration"], rows))
    return "\n".join(lines) + "\n"


def _section_oracle(log: dict) -> str:
    oracle = log.get("gt_oracle_result")
    if not oracle:
        return ""
    passed = oracle.get("passed")
    model = oracle.get("model", "unknown")
    duration = oracle.get("duration_sec")
    error = oracle.get("error")

    status = "PASS" if passed is True else "FAIL" if passed is False else "ERROR"

    parts = ["## GT Oracle Check\n"]
    rows = [
        ("Status", f"**{status}**"),
        ("Model", f"`{model}`"),
        ("Duration", _fmt_dur(duration)),
    ]
    if oracle.get("reward") is not None:
        rows.append(("Canonical reward", str(oracle["reward"])))
    if error:
        rows.append(("Error", error[:200]))
    parts.append(_md_table(["Key", "Value"], rows))
    return "\n".join(parts) + "\n"


def _section_intervention_history(log: dict) -> str:
    """Render intervention history as a table showing score progression."""
    history = log.get("intervention_history", [])
    if not history:
        return ""

    parts = ["## Intervention History\n"]

    rows: list[tuple] = []
    for entry in history:
        num = entry.get("intervention_number", "?")
        trigger = entry.get("trigger", "?")

        # Surrogate score
        sr = entry.get("surrogate_result")
        if sr:
            s_passed = sr.get("tests_passed", 0)
            s_total = sr.get("total_tests", 0)
            s_rate = sr.get("pass_rate", 0.0)
            surrogate_str = f"{s_passed}/{s_total} ({s_rate:.0%})"
        else:
            surrogate_str = "n/a"

        # GT score
        gt = entry.get("gt_result")
        if gt and gt.get("total_tests") is not None:
            g_passed = gt.get("tests_passed", 0)
            g_total = gt.get("total_tests", 0)
            g_rate = gt.get("pass_rate", 0.0)
            reward = gt.get("reward")
            gt_str = f"{g_passed}/{g_total} ({g_rate:.0%} tests)"
            if reward is not None:
                gt_str += f", reward={reward}"
        else:
            gt_str = "n/a"

        rows.append((str(num), trigger, surrogate_str, gt_str))

    parts.append(_md_table(["#", "Trigger", "Surrogate", "GT Score"], rows))
    parts.append("")
    return "\n".join(parts)


def _section_tokens(log: dict) -> str:
    tok = log.get("token_usage", {})
    if not tok:
        return ""

    agent_in = tok.get("agent_input_tokens", 0)
    agent_out = tok.get("agent_output_tokens", 0)

    rows = [
        (
            "Agent (execution)",
            _fmt_num(agent_in),
            _fmt_num(agent_out),
            _fmt_num(agent_in + agent_out),
        ),
    ]

    parts = ["## Token Usage\n"]
    parts.append(_md_table(["Component", "Input", "Output", "Total"], rows))
    return "\n".join(parts) + "\n"


# ──────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────


def _md_table(headers: list[str], rows: list[tuple]) -> str:
    """Build a Markdown table string."""
    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("-----" for _ in headers) + "|")
    for row in rows:
        cells = [str(c).replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _fmt_dur(sec: float | None) -> str:
    if sec is None:
        return "n/a"
    return f"{sec:.1f}s"


def _fmt_num(n: int | float) -> str:
    return f"{int(n):,}"


def _format_timestamp(ts: str) -> str:
    """Format an ISO timestamp to a shorter display form."""
    if not ts:
        return "n/a"
    # Try to parse and reformat
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return ts
