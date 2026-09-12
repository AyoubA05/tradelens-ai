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
        # A bare name, not `anything.load_prompt(...)`, whatever `anything` is.
        and isinstance(expr.func, ast.Name)
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


# ── E6 review: the ways around this sweep, closed ─────────────────────────
#
# The checks above trust two things they never verified: that `load_prompt`
# in a service IS ai_client's function, and that the Partner's named
# constants still hold the literal they were bound to. The E6 reviewer broke
# the first (a module-level `def load_prompt(name): return str(notes)` in
# weekly.py passed every test above) and described the second
# (`global _SCOPE_GUARD; _SCOPE_GUARD += notes`). Each detector below is also
# run against a hostile snippet, so an all-clear cannot come from a matcher
# that never fires.

AI_CLIENT = SERVICES / "ai_client.py"
AI_CLIENT_MODULE = "src.tradelens.services.ai_client"
_STORE = (ast.Store, ast.Del)


def _service_trees():
    for path in sorted(SERVICES.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_names(tree):
    """Names this module binds to modules through an import statement."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _is_module_target(expr, modules):
    """`sys.modules[...]`, an imported module name (or an attribute of one), or a
    dynamic import. An ORM row or any other data object is not a module target:
    services legitimately write fields with `setattr(row, key, value)`."""
    if isinstance(expr, ast.Subscript):
        value = expr.value
        if isinstance(value, ast.Call):
            # `getattr(sys, "modules")[__name__]` (round-4 review R2).
            return True
        return (isinstance(value, ast.Attribute) and value.attr == "modules") or (
            isinstance(value, ast.Name) and value.id == "modules"
        )
    if isinstance(expr, ast.Call):
        return _call_name(expr) in ("__import__", "import_module")
    root = expr
    while isinstance(root, ast.Attribute):
        root = root.value
    return isinstance(root, ast.Name) and root.id in modules


_AI_CLIENT_FUNCTIONS = ("load_prompt", "chat", "vision", "converse")


def _rebindings(tree, name, *, is_ai_client):
    """Every way a module could make `name` mean something other than ai_client's."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            if isinstance(node.ctx, _STORE):
                found.append("assigned")
        elif isinstance(node, ast.arg) and node.arg == name:
            found.append("parameter")
        elif isinstance(node, ast.Attribute) and node.attr == name:
            # `import …ai_client as ai; ai.load_prompt = g` (delta review M1).
            if isinstance(node.ctx, _STORE):
                found.append("attribute store")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name and not (is_ai_client and node in tree.body):
                found.append("defined")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    found.append("star import")
                elif (alias.asname or alias.name.split(".")[-1]) == name:
                    if not (
                        isinstance(node, ast.ImportFrom)
                        and node.level == 0
                        and node.module == AI_CLIENT_MODULE
                        and alias.name == name
                    ):
                        found.append("imported from elsewhere")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if name in node.names:
                found.append("global")
        elif _call_name(node) in ("setattr", "delattr") and len(node.args) >= 2:
            attr = node.args[1]
            # A built-up name (`"load" + "_prompt"`) is refused outright: a
            # detector that reads only literals cannot see what it rebinds
            # (round-3 review N1).
            literal = isinstance(attr, ast.Constant)
            if (literal and attr.value == name) or (
                not literal and _is_module_target(node.args[0], _module_names(tree))
            ):
                found.append("setattr")
    return found


def _load_prompt_rebindings(tree, *, is_ai_client):
    return _rebindings(tree, "load_prompt", is_ai_client=is_ai_client)


def _constant_rebindings(tree, names):
    """Stores to the Partner's system constants beyond their one binding."""
    found = []
    for name in names:
        top = [
            n
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
        ]
        stores = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, _STORE)
        ]
        if len(top) != 1 or len(stores) != 1:
            found.append((name, "rebound"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            found += [(n, "global") for n in node.names if n in names]
        elif isinstance(node, ast.Attribute) and node.attr in names:
            if isinstance(node.ctx, _STORE):
                found.append((node.attr, "attribute store"))
        elif _call_name(node) in ("setattr", "delattr") and len(node.args) >= 2:
            name = node.args[1]
            literal = isinstance(name, ast.Constant)
            if (literal and name.value in names) or (
                not literal and _is_module_target(node.args[0], _module_names(tree))
            ):
                found.append((getattr(name, "value", "<built>"), "setattr"))
    return found


def test_load_prompt_is_only_ever_ai_clients_function():
    for path, tree in _service_trees():
        assert (
            _load_prompt_rebindings(tree, is_ai_client=path == AI_CLIENT) == []
        ), path.name


def test_the_load_prompt_detector_fires_on_hostile_modules():
    hostile = [
        "def load_prompt(name):\n    return str(notes)\n",
        "load_prompt = lambda name: notes\n",
        "from src.tradelens.services.other import load_prompt\n",
        "from src.tradelens.services.ai_client import chat as load_prompt\n",
        "from src.tradelens.services.ai_client import *\n",
        "from .ai_client import load_prompt\n",
        "def f():\n    global load_prompt\n    load_prompt = g\n",
        "def f(load_prompt=g):\n    pass\n",
        "setattr(module, 'load_prompt', g)\n",
        'setattr(_s.modules[__name__], "load" + "_prompt", g)\n',
        'delattr(ai_client, "load_prompt")\n',
        "for load_prompt in things:\n    pass\n",
        "import src.tradelens.services.ai_client as ai\nai.load_prompt = g\n",
    ]
    for source in hostile:
        assert _load_prompt_rebindings(ast.parse(source), is_ai_client=False), source
    clean = "from src.tradelens.services.ai_client import chat, load_prompt\n"
    assert _load_prompt_rebindings(ast.parse(clean), is_ai_client=False) == []


def test_the_partner_system_constants_are_bound_once_and_never_rebound():
    for path, tree in _service_trees():
        if path.name == "partner.py":
            assert _constant_rebindings(tree, PARTNER_SYSTEM_CONSTANTS) == []
        else:
            # Other modules may not bind these names at all, nor reach in.
            stray = [
                n
                for n in ast.walk(tree)
                if (isinstance(n, ast.Name) and n.id in PARTNER_SYSTEM_CONSTANTS)
                or (
                    isinstance(n, ast.Attribute)
                    and n.attr in PARTNER_SYSTEM_CONSTANTS
                    and isinstance(n.ctx, _STORE)
                )
            ]
            assert stray == [], path.name


def test_the_constant_detector_fires_on_hostile_modules():
    names = {"_SCOPE_GUARD"}
    base = '_SCOPE_GUARD = "literal"\n'
    hostile = [
        base + "def f():\n    global _SCOPE_GUARD\n    _SCOPE_GUARD += notes\n",
        base + "_SCOPE_GUARD = _SCOPE_GUARD + notes\n",
        base + "partner._SCOPE_GUARD = notes\n",
        base + "setattr(partner, '_SCOPE_GUARD', notes)\n",
        base + 'setattr(_s.modules[__name__], "_SCOPE" + "_GUARD", "x")\n',
        "if flag:\n    _SCOPE_GUARD = 'a'\nelse:\n    _SCOPE_GUARD = 'b'\n",
    ]
    for source in hostile:
        assert _constant_rebindings(ast.parse(source), names), source
    assert _constant_rebindings(ast.parse(base), names) == []


def test_ai_client_builds_the_system_field_only_from_its_own_parameters():
    """`_build_system` is where a system message becomes the API's system field.

    It may compose `system_message` and `few_shot` and nothing else — and no
    service passes `few_shot` (pinned above) while `converse` does not accept
    it at all. `_complete` may bind the outgoing `system` only from it.
    """
    tree = ast.parse(AI_CLIENT.read_text(encoding="utf-8"))
    build = next(f for f in _functions(tree) if f.name == "_build_system")
    assert [a.arg for a in build.args.args] == [
        "system_message",
        "few_shot",
        "cache_system",
    ]
    names = {n.id for n in ast.walk(build) if isinstance(n, ast.Name)}
    allowed = {
        "system_message",
        "few_shot",
        "cache_system",
        "text",
        "Optional",
        "str",
        "bool",
    }
    assert names <= allowed, names - allowed

    complete = next(f for f in _functions(tree) if f.name == "_complete")
    binds = [
        n
        for n in ast.walk(complete)
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id == "system"
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        )
    ]
    assert binds, "no outgoing system field found in _complete"
    for node in binds:
        assert isinstance(node, ast.Assign), ast.dump(node)[:120]
        assert _call_name(node.value) == "_build_system", ast.dump(node.value)[:120]


def test_an_attribute_call_is_not_a_literal_prompt():
    assert not _is_literal_prompt(
        ast.parse('other.load_prompt("journal_v1")').body[0].value
    )


# ── Delta review (post-f9444f6): four more evasions, closed ───────────────

_DYNAMIC_NAMES = {
    "globals",
    "vars",
    "locals",
    "exec",
    "eval",
    "compile",
    "__import__",
}
_DYNAMIC_ATTRS = {
    "__dict__",
    "__globals__",
    "import_module",
    # Round-4 review: `_me = sys.modules[__name__]` then `setattr(_me, …)` (R1),
    # and `object.__setattr__(module, …)` (R3).
    "modules",
    "__setattr__",
    "__delattr__",
}


def _dynamic_namespace_access(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_ATTRS:
            found.append(node.attr)
        elif _call_name(node) in ("setattr", "delattr") and len(node.args) >= 2:
            # A built-up attribute name on a MODULE (round-3 review N1/N6).
            if not isinstance(node.args[1], ast.Constant) and _is_module_target(
                node.args[0], _module_names(tree)
            ):
                found.append("module " + _call_name(node))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            if any(m == "importlib" or m.startswith("importlib.") for m in modules):
                found.append("importlib")
    return found


def test_no_service_reaches_a_module_namespace_dynamically():
    """`globals()["_SCOPE" + "_GUARD"] = notes` rebinds a system constant with no
    Name or Attribute store for the detectors above to see (delta review M3).
    No service needs dynamic namespace access, so none may have it."""
    for path, tree in _service_trees():
        assert _dynamic_namespace_access(tree) == [], path.name


def test_the_dynamic_access_detector_fires_on_hostile_modules():
    hostile = [
        'globals()["_SCOPE" + "_GUARD"] = notes\n',
        'vars(partner)["_SCOPE_GUARD"] = notes\n',
        'partner.__dict__["_SCOPE_GUARD"] = notes\n',
        'build.__globals__["_SCOPE_GUARD"] = notes\n',
        "import importlib\n",
        'import sys\nsetattr(sys.modules[__name__], "_SCOPE" + "_GUARD", "x")\n',
        'import src.tradelens.services.partner as p\ndelattr(p, "_SCOPE" + "_GUARD")\n',
        "from importlib import import_module\n",
        'exec("_SCOPE_GUARD = notes")\n',
    ]
    for source in hostile:
        assert _dynamic_namespace_access(ast.parse(source)), source
    assert _dynamic_namespace_access(ast.parse("import re\nre.compile('x')\n")) == []


def test_load_prompt_reads_only_the_versioned_prompt_file():
    """ai_client's own `load_prompt` is exempt from the rebinding check because
    it IS the function, so its body is pinned instead: it reads
    prompts/{name}.txt and nothing else. No environment variable, database,
    network or module state can reach a system message through it (delta
    review M2)."""
    tree = ast.parse(AI_CLIENT.read_text(encoding="utf-8"))
    func = next(
        f
        for f in tree.body
        if isinstance(f, ast.FunctionDef) and f.name == "load_prompt"
    )
    assert [a.arg for a in func.args.args] == ["name"]
    names = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    assert names <= {"name", "path", "_PROMPTS_DIR", "FileNotFoundError", "str"}, names
    attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
    assert attrs <= {"exists", "read_text", "strip"}, attrs
    # The one operator allowed is the path join `_PROMPTS_DIR / f"{name}.txt"`.
    # Anything else — `+ os.environ[...]`, `% extra` — is text composition.
    for node in ast.walk(func):
        if isinstance(node, ast.BinOp):
            assert isinstance(node.op, ast.Div), ast.dump(node)[:120]
            assert isinstance(node.left, ast.Name) and node.left.id == "_PROMPTS_DIR"

    prompts_dir = next(
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_PROMPTS_DIR" for t in n.targets)
    )
    dir_names = {n.id for n in ast.walk(prompts_dir.value) if isinstance(n, ast.Name)}
    dir_attrs = {
        n.attr for n in ast.walk(prompts_dir.value) if isinstance(n, ast.Attribute)
    }
    assert "os" not in dir_names and not dir_attrs & {"environ", "getenv"}, (
        dir_names,
        dir_attrs,
    )


_AI_ENTRY_POINTS = {
    "chat",
    "vision",
    "converse",
    "_complete",
    "_build_system",
    "load_prompt",
}


_PROTECTED_ATTRS = _AI_ENTRY_POINTS | {
    "_PROMPTS_DIR",
    "_SCOPE_GUARD",
    "_PER_TRADE_QA_PREAMBLE",
    "build_partner_system",
    "partner_reply",
}


def _ai_entry_points_used(tree):
    """Outside services/: no AI entry point may be imported, called or rewired."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "ai_client":
                    found.append("imports the ai_client module")
                elif alias.name == "*" and (node.module or "").startswith(
                    "src.tradelens.services"
                ):
                    found.append("star import from services")
                elif alias.name in _AI_ENTRY_POINTS:
                    # From ANY module: a service re-exports `converse` simply by
                    # importing it (round-3 review N4).
                    found.append(alias.name)
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.endswith("ai_client")]
        elif isinstance(node, ast.Call) and _call_name(node) in {
            "chat",
            "vision",
            "converse",
            "setattr",
            "delattr",
        }:
            # Bare or through any module attribute, e.g. `weekly.chat(...)` (N5).
            found.append("calls " + _call_name(node))
        elif isinstance(node, ast.Attribute) and node.attr in _PROTECTED_ATTRS:
            if isinstance(node.ctx, _STORE) or node.attr in (
                _AI_ENTRY_POINTS - {"chat", "vision"}
            ):
                found.append(node.attr)
    return found


def test_no_ai_entry_point_is_reachable_outside_services():
    """The call-site sweep reads services/ only, so a new
    `converse(system_message=…)` under api/, ui/ or scripts/ would be invisible
    to it (delta review M4). Nothing outside services/ may import or reach an
    AI entry point; every call site therefore stays inside the pinned set."""
    root = SERVICES.parents[2]
    paths = [
        p
        for base in ("src", "scripts")
        for p in sorted((root / base).rglob("*.py"))
        if SERVICES not in p.parents
    ]
    assert len(paths) > 20
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert _ai_entry_points_used(tree) == [], str(path.relative_to(root))


def test_the_outside_services_detector_fires_on_hostile_modules():
    hostile = [
        "from src.tradelens.services.ai_client import converse\n",
        "from src.tradelens.services.ai_client import *\n",
        "from src.tradelens.services import ai_client\n",
        "import src.tradelens.services.ai_client as ai\n",
        "reply = client.converse(system_message=text)\n",
        "from src.tradelens.services.partner import converse\n",
        "from src.tradelens.services import weekly as w\nw.chat([], system_message=n)\n",
        "import src.tradelens.services.weekly as w\nw.vision(img, notes)\n",
        "import src.tradelens.services.ai_client\n",
        'setattr(module, "load" + "_prompt", g)\n',
        "partner._SCOPE_GUARD = notes\n",
        "ai._PROMPTS_DIR = somewhere\n",
    ]
    for source in hostile:
        assert _ai_entry_points_used(ast.parse(source)), source
    allowed = "from src.tradelens.services.ai_client import AIParseError, has_api_key\n"
    assert _ai_entry_points_used(ast.parse(allowed)) == []


# ── Round-3 review: the prompts directory and the other ai_client functions ─


def _repo_trees():
    root = SERVICES.parents[2]
    for base in ("src", "scripts"):
        for path in sorted((root / base).rglob("*.py")):
            yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_ai_client_functions_are_never_rebound_in_a_service():
    """`chat = functools.partial(chat, system_message=…)` would leave every call
    site looking pinned while changing what reaches the model (round-3 review
    N7). `chat`, `vision` and `converse` are held to the same rule as
    `load_prompt`."""
    for path, tree in _service_trees():
        for name in _AI_CLIENT_FUNCTIONS:
            found = _rebindings(tree, name, is_ai_client=path == AI_CLIENT)
            assert found == [], (path.name, name, found)


def test_the_rebinding_detector_fires_for_every_ai_client_function():
    for name in ("chat", "vision", "converse"):
        hostile = [
            "import functools\n{0} = functools.partial({0}, system_message=x)\n",
            "from src.tradelens.services.partner import {0}\n",
            "def {0}(*a, **k):\n    return None\n",
        ]
        for template in hostile:
            source = template.format(name)
            assert _rebindings(ast.parse(source), name, is_ai_client=False), source
        clean = "from src.tradelens.services.ai_client import {}\n".format(name)
        assert _rebindings(ast.parse(clean), name, is_ai_client=False) == []


def test_the_prompts_directory_is_bound_once_to_the_repository_and_never_moved():
    """`load_prompt` reads `_PROMPTS_DIR / name`, so moving the directory moves
    every system prompt. A second binding inside ai_client (round-3 review N3)
    or a store from any other module (N2) could point it at a directory a user
    can write. It is bound exactly once, to exactly this expression, and
    `Path` there is pathlib's."""
    tree = ast.parse(AI_CLIENT.read_text(encoding="utf-8"))
    stores = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Name)
        and n.id == "_PROMPTS_DIR"
        and isinstance(n.ctx, _STORE)
    ]
    assert len(stores) == 1, len(stores)
    binding = next(
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_PROMPTS_DIR" for t in n.targets)
    )
    expected = ast.parse('Path(__file__).resolve().parents[3] / "prompts"', mode="eval")
    assert ast.dump(binding.value) == ast.dump(expected.body)
    assert any(
        isinstance(n, ast.ImportFrom)
        and n.module == "pathlib"
        and any(a.name == "Path" and a.asname is None for a in n.names)
        for n in tree.body
    )
    assert not [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == "Path" and isinstance(n.ctx, _STORE)
    ]

    for path, other in _repo_trees():
        for node in ast.walk(other):
            if isinstance(node, ast.Attribute) and node.attr == "_PROMPTS_DIR":
                assert not isinstance(node.ctx, _STORE), str(path)
            if isinstance(node, ast.Name) and node.id == "_PROMPTS_DIR":
                assert path == AI_CLIENT, str(path)


# What this file is, stated plainly: an AST tripwire over the evasions review
# has actually found (four rounds, listed in the Phase 8 handoff). It makes each
# of them fail loudly and keeps new AI call sites inside a reviewed set. It is
# not a proof that no route to the system slot exists; Python can always reach
# further than a static reading. Reviewers should keep adding the next one.


def test_setattr_on_a_data_object_is_not_a_module_rewrite():
    """Services write ORM fields with `setattr(row, key, value)` (eight call
    sites today). The module-rewrite detectors must leave those alone while
    still refusing the same call aimed at a module."""
    for source in [
        "setattr(row, key, value)\n",
        "setattr(trade, field, f'{existing}')\n",
        "delattr(obj, name)\n",
    ]:
        tree = ast.parse(source)
        assert _dynamic_namespace_access(tree) == [], source
        assert _rebindings(tree, "load_prompt", is_ai_client=False) == [], source
    for source in [
        "import src.tradelens.services.ai_client as ai\nsetattr(ai, name, g)\n",
        "import sys\nsetattr(sys.modules[__name__], name, g)\n",
        "setattr(__import__('x'), name, g)\n",
    ]:
        tree = ast.parse(source)
        assert _dynamic_namespace_access(tree), source
        assert _rebindings(tree, "load_prompt", is_ai_client=False), source


# ── Round-4 review: AI entry points used as values, or under another name ──


def _indirect_references(tree):
    """An AI entry point that is not simply called.

    `_ask = functools.partial(chat, system_message=notes)` then `_ask([])`
    (round-4 review R4) and `from …ai_client import chat as ask` both produce
    calls the pinned call-site set cannot see, because they are not named
    `chat`. In services these functions may only ever be called directly.
    A literal `getattr(x, "modules")` is the R2 route to the same place.
    """
    call_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id in _AI_CLIENT_FUNCTIONS
            and isinstance(node.ctx, ast.Load)
            and id(node) not in call_funcs
        ):
            found.append(("used as a value", node.id))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _AI_CLIENT_FUNCTIONS and alias.asname not in (
                    None,
                    alias.name,
                ):
                    found.append(("imported under another name", alias.name))
        elif _call_name(node) == "getattr" and len(node.args) >= 2:
            attr = node.args[1]
            if isinstance(attr, ast.Constant) and (
                attr.value in _DYNAMIC_ATTRS or attr.value in _AI_CLIENT_FUNCTIONS
            ):
                found.append(("getattr", attr.value))
    return found


def test_ai_entry_points_are_only_ever_called_directly_in_services():
    for path, tree in _service_trees():
        assert _indirect_references(tree) == [], path.name


def test_the_indirect_reference_detector_fires_on_hostile_modules():
    hostile = [
        "import functools\n_ask = functools.partial(chat, system_message=notes)\n",
        "ask = converse\n",
        "run(vision, image)\n",
        "handlers = {'prompt': load_prompt}\n",
        "from src.tradelens.services.ai_client import chat as ask\n",
        "import sys\nmods = getattr(sys, 'modules')\n",
        "fn = getattr(ai_client, 'converse')\n",
    ]
    for source in hostile:
        assert _indirect_references(ast.parse(source)), source
    clean = [
        "from src.tradelens.services.ai_client import chat, load_prompt\n"
        "content = chat([], system_message=load_prompt('journal_v1'))\n",
        "value = getattr(obj, key, None)\n",
    ]
    for source in clean:
        assert _indirect_references(ast.parse(source)) == [], source


def test_the_dynamic_detector_catches_the_round_4_module_routes():
    hostile = [
        "import sys\n_me = sys.modules[__name__]\nsetattr(_me, 'a' + 'b', 1)\n",
        "object.__setattr__(target, 'a' + 'b', 1)\n",
        "object.__delattr__(target, 'a')\n",
    ]
    for source in hostile:
        assert _dynamic_namespace_access(ast.parse(source)), source
    tree = ast.parse(
        "import sys\nsetattr(getattr(sys, 'modules')[__name__], 'a' + 'b', 1)\n"
    )
    assert _indirect_references(tree) and _rebindings(
        tree, "load_prompt", is_ai_client=False
    )
