"""Phase 8 E2 — every AI call site's system message, read from the source.

The trust rule: trader-authored and model-read text is USER-ROLE DATA, never
system authority. A system message may contain only constant,
repository-owned text.

This walks the AST of every module in `services/` rather than calling the
functions, because the property is about what a call site is ABLE to put in
the system slot, not what one fixture happened to pass. Two things make it
bite:

* The set of call sites is pinned. A new `chat(` / `vision(` / `converse(`
  anywhere in `services/` fails here until someone has looked at what it puts
  in the system slot and added it on purpose.
* A system message may be built only from `load_prompt("<literal>")` — or,
  for the Partner, from `build_partner_system(...)`, whose own body is held
  to the same constants. No f-string, no `+`, no `+=`, no `.format`, no
  `.join` over anything that is not a named repository constant.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SERVICES = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "tradelens" / "services"
)
AI_CALLS = {"chat", "vision", "converse"}

# (module, enclosing function) for every AI call in services/. Pinned: adding
# one is a deliberate act that must pass through this file.
EXPECTED_CALL_SITES = {
    ("debrief.py", "generate_debrief"),
    ("grading.py", "grade_trade"),
    ("journal.py", "generate_journal"),
    ("partner.py", "partner_reply"),
    ("patterns.py", "generate_cards"),
    ("trade_summary.py", "generate_trade_summary"),
    ("vision.py", "analyze_screenshot"),
    ("vision.py", "analyze_screenshot_v3"),
    ("weekly.py", "generate_weekly_review"),
}

# The only names build_partner_system may compose from.
PARTNER_SYSTEM_CONSTANTS = {"_SCOPE_GUARD", "_PER_TRADE_QA_PREAMBLE"}


def _modules():
    for path in sorted(SERVICES.glob("*.py")):
        if path.name in ("ai_client.py", "__init__.py"):
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _call_name(node):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _functions(tree):
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _ai_calls(func):
    return [n for n in ast.walk(func) if _call_name(n) in AI_CALLS]


def _is_literal_prompt(expr):
    """`load_prompt("name")` with a string literal and nothing else."""
    return (
        _call_name(expr) == "load_prompt"
        and len(expr.args) == 1
        and not expr.keywords
        and isinstance(expr.args[0], ast.Constant)
        and isinstance(expr.args[0].value, str)
    )


def _is_partner_system(expr):
    return _call_name(expr) == "build_partner_system" and not expr.args


def _system_arg(call):
    for kw in call.keywords:
        if kw.arg == "system_message":
            return kw.value
    return None


def _assignments_to(func, name):
    """Every way `name` is bound inside `func`, including the ones that grow it."""
    out = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                out.append(node.value)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                # An AugAssign is never a constant composition: record the
                # node itself so the caller refuses it.
                out.append(node if isinstance(node, ast.AugAssign) else node.value)
        elif isinstance(node, (ast.For, ast.With, ast.NamedExpr)):
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name) and target.id == name:
                out.append(node)
    return out


def _collect():
    sites = {}
    for path, tree in _modules():
        for func in _functions(tree):
            for call in _ai_calls(func):
                sites.setdefault((path.name, func.name), []).append((func, call))
    return sites


def test_the_set_of_ai_call_sites_is_pinned():
    assert set(_collect()) == EXPECTED_CALL_SITES


@pytest.mark.parametrize("site", sorted(EXPECTED_CALL_SITES))
def test_every_system_message_is_repository_constant_text(site):
    module, _function = site
    for func, call in _collect()[site]:
        arg = _system_arg(call)
        assert arg is not None, "{}: AI call without an explicit system_message".format(
            site
        )

        allowed = _is_partner_system if module == "partner.py" else _is_literal_prompt
        if isinstance(arg, ast.Name):
            bound = _assignments_to(func, arg.id)
            assert bound, "{}: {} is never assigned".format(site, arg.id)
            for value in bound:
                assert allowed(value), "{}: {} is built from {}".format(
                    site, arg.id, ast.dump(value)[:160]
                )
            # Not a parameter: a system message the caller passes in is a
            # system message the caller controls.
            params = {a.arg for a in func.args.args + func.args.kwonlyargs}
            assert arg.id not in params, "{}: system message is a parameter".format(
                site
            )
        else:
            assert allowed(arg), "{}: system_message={}".format(
                site, ast.dump(arg)[:160]
            )


def test_no_ai_call_passes_few_shot_text():
    """`few_shot` is routed into the system slot by ai_client — it must stay unused."""
    for site, pairs in _collect().items():
        for _func, call in pairs:
            assert all(kw.arg != "few_shot" for kw in call.keywords), site


def test_build_partner_system_composes_only_repository_constants():
    tree = ast.parse((SERVICES / "partner.py").read_text(encoding="utf-8"))
    func = next(f for f in _functions(tree) if f.name == "build_partner_system")

    # Keyword-only flag, no positional data parameter to smuggle text through.
    assert not func.args.args and not func.args.vararg and not func.args.kwarg
    assert [a.arg for a in func.args.kwonlyargs] == ["per_trade_qa"]

    names = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    locals_ = {"parts", "per_trade_qa"}
    # `bool`/`str` appear only in the signature's annotations.
    builtins_ = {"load_prompt", "bool", "str"}
    assert names <= PARTNER_SYSTEM_CONSTANTS | locals_ | builtins_, names - (
        PARTNER_SYSTEM_CONSTANTS | locals_ | builtins_
    )
    for node in ast.walk(func):
        # No f-strings, %-formatting or .format() anywhere in the builder.
        assert not isinstance(node, ast.JoinedStr)
        assert not (
            isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add))
        )
        assert _call_name(node) != "format"
        if _call_name(node) == "load_prompt":
            assert _is_literal_prompt(node)

    # Each constant it composes from is a module-level string literal.
    module_consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_consts[target.id] = node.value
    for name in PARTNER_SYSTEM_CONSTANTS:
        value = module_consts.get(name)
        assert isinstance(value, ast.Constant) and isinstance(value.value, str), name


def test_the_sweep_itself_would_catch_data_in_the_system_slot():
    """The detectors are exercised on hostile snippets, not only on the tree.

    A sweep that returns "all clear" because its matcher never matches
    anything is the failure this file exists to prevent.
    """
    hostile = [
        'system_message = load_prompt("journal_v1") + strategy_block',
        "system_message = f\"{load_prompt('journal_v1')}{notes}\"",
        "system_message = load_prompt(name)",
        'system_message = "\\n".join([load_prompt("x"), notes])',
    ]
    for snippet in hostile:
        value = ast.parse(snippet).body[0].value
        assert not _is_literal_prompt(value), snippet
        assert not _is_partner_system(value), snippet

    grown = ast.parse(
        'def f():\n    system_message = load_prompt("x")\n    system_message += notes\n'
    ).body[0]
    bound = _assignments_to(grown, "system_message")
    assert not all(_is_literal_prompt(v) for v in bound)

    assert _is_literal_prompt(ast.parse('load_prompt("journal_v1")').body[0].value)
    assert _is_partner_system(
        ast.parse("build_partner_system(per_trade_qa=True)").body[0].value
    )
    assert not _is_partner_system(
        ast.parse("build_partner_system(notes)").body[0].value
    )
