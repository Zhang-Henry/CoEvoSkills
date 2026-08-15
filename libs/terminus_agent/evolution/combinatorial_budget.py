"""Static guardrails for obviously unbounded combinatorial evolution commands.

The evolution agent is allowed to explore, but a single generated command must
not enumerate a whole runtime domain through Cartesian products, permutations,
or powersets without one fail-closed *global* budget.  A timeout remains the
last-resort safety net; this module rejects the most common runaway shape before
the command starts so the model can replace it with beam, local, or greedy
search.

This is deliberately a performance guard, not a task oracle.  It examines only
the proposed command/source shape and never task outputs or evaluator data.
"""

from __future__ import annotations

import ast
import re


_COMBINATORIAL_NAMES = {
    "combinations",
    "combinations_with_replacement",
    "permutations",
    "powerset",
    "product",
}

_FULL_DOMAIN_RE = re.compile(
    r"\b(?:all_[a-z0-9_]*|land_tiles?|map_tiles?|tiles?|candidates?|"
    r"candidate_positions?|valid_positions?|positions?|pos_lists?|subsets?)\b",
    re.IGNORECASE,
)

_COUNTER_RE = re.compile(
    r"(?:evaluat|expansion|visited|trial|candidate|state|node|iteration|step|count)",
    re.IGNORECASE,
)

_BUDGET_RE = re.compile(
    r"(?:budget|deadline|max_(?:global_)?(?:evaluations?|expansions?|trials?|"
    r"candidates?|states?|nodes?|iterations?|steps?|seconds?))",
    re.IGNORECASE,
)

_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?[^\n]*\n"
    r"(.*?)\n\1(?:\s*(?:\n|$))",
    re.DOTALL,
)

_PYTHON_PATH_RE = re.compile(
    r"\bpython(?:\d+(?:\.\d+)?)?\s+"
    r"(?:-[A-Za-z]+\s+)*"
    r"(/[A-Za-z0-9_./-]+\.py)(?=\s|$|[;&|])"
)


def referenced_python_scripts(command_text: str) -> tuple[str, ...]:
    """Return safe absolute Python script paths directly executed by a command."""
    return tuple(dict.fromkeys(_PYTHON_PATH_RE.findall(command_text)))


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _contains_fail_closed_exit(statements: list[ast.stmt]) -> bool:
    """Return whether a budget guard exits the complete search scope.

    ``break`` and ``continue`` are intentionally insufficient: in nested search
    they usually limit only the innermost or current product. ``return`` or
    ``raise`` exits the containing
    search function (or module) and therefore establishes a real global cap.
    """
    return any(isinstance(node, (ast.Return, ast.Raise)) for stmt in statements for node in ast.walk(stmt))


def _test_has_budget(test: ast.AST) -> bool:
    rendered = ast.unparse(test).lower()
    if "deadline" in rendered or "monotonic" in rendered:
        return True
    if _BUDGET_RE.search(rendered):
        return True

    # A literal global guard such as ``if evaluated >= 5000: return best`` is
    # also explicit even if the author did not name the constant "budget".
    has_counter = bool(_COUNTER_RE.search(rendered))
    has_positive_limit = any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value > 0
        for node in ast.walk(test)
    )
    return has_counter and has_positive_limit


def _scope_has_global_budget(scope: ast.AST) -> bool:
    for node in ast.walk(scope):
        if not isinstance(node, ast.If):
            continue
        if _test_has_budget(node.test) and _contains_fail_closed_exit(node.body):
            return True
    return False


def _max_loop_depth(scope: ast.AST) -> int:
    maximum = 0

    def visit(node: ast.AST, depth: int) -> None:
        nonlocal maximum
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            depth += 1
            maximum = max(maximum, depth)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            depth += len(node.generators)
            maximum = max(maximum, depth)
        for child in ast.iter_child_nodes(node):
            # Nested functions are separate search scopes.
            if child is not scope and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            visit(child, depth)

    visit(scope, 0)
    return maximum


def _scope_issue(scope: ast.AST, source: str) -> str | None:
    calls = {
        _call_name(node)
        for node in ast.walk(scope)
        if isinstance(node, ast.Call) and _call_name(node) in _COMBINATORIAL_NAMES
    }
    subset_shift = any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.LShift)
        and isinstance(node.left, ast.Constant)
        and node.left.value == 1
        for node in ast.walk(scope)
    )
    if not calls and not subset_shift:
        return None

    if not _FULL_DOMAIN_RE.search(source):
        return None

    loop_depth = _max_loop_depth(scope)
    direct_explosion = bool(calls & {"product", "permutations", "powerset"}) or subset_shift
    if not direct_explosion and loop_depth < 2:
        return None

    if _scope_has_global_budget(scope):
        return None

    names = sorted(calls) or ["bitmask powerset"]
    return (
        "detected full-domain nested search using "
        f"{', '.join(names)} without a fail-closed global evaluation/deadline budget"
    )


def _module_scopes(tree: ast.Module, source: str) -> list[tuple[ast.AST, str]]:
    scopes: list[tuple[ast.AST, str]] = []
    top_level = ast.Module(
        body=[
            node
            for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ],
        type_ignores=[],
    )
    scopes.append((top_level, source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node) or source
            scopes.append((node, segment))
    return scopes


def _source_issue(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Shell fragments and partially generated files still receive a narrow
        # textual fallback.  Require all three signals to avoid blocking normal
        # data-processing loops.
        calls = sorted(
            name
            for name in _COMBINATORIAL_NAMES
            if re.search(rf"\b{re.escape(name)}\s*\(", source)
        )
        subset_shift = bool(re.search(r"\b1\s*<<\s*len\s*\(", source))
        nested = len(re.findall(r"(?m)^\s*for\s+", source)) >= 2
        has_global_exit = bool(
            re.search(
                r"(?is)(?:budget|deadline|max_(?:global_)?(?:evaluations?|nodes?|"
                r"states?|trials?|iterations?)).{0,240}\b(?:return|raise)\b",
                source,
            )
        )
        if (
            (calls or subset_shift)
            and nested
            and _FULL_DOMAIN_RE.search(source)
            and not has_global_exit
        ):
            names = calls or ["bitmask powerset"]
            return (
                "detected full-domain nested search using "
                f"{', '.join(names)} without a fail-closed global evaluation/deadline budget"
            )
        return None

    for scope, segment in _module_scopes(tree, source):
        issue = _scope_issue(scope, segment)
        if issue:
            return issue
    return None


def combinatorial_search_budget_issue(
    command_text: str,
    *,
    referenced_sources: tuple[str, ...] = (),
) -> str | None:
    """Return an answer-free rejection reason for an unbounded search command."""
    sources = [match.group(2) for match in _HEREDOC_RE.finditer(command_text)]
    if not sources:
        sources.append(command_text)
    sources.extend(referenced_sources)

    for source in sources:
        issue = _source_issue(source)
        if issue:
            return issue
    return None
