"""Standalone runner for this project's pure, dependency-free test
modules, for sandboxes without pytest installed.

These files are ordinary pytest (test classes/functions, `assert`
statements, `pytest.raises`/`pytest.approx`, a few `@pytest.fixture`s
with no further dependencies, one `@pytest.mark.parametrize`) — nothing
that needs a database, network, or third-party package beyond `httpx`
(present in this sandbox). This script collects every `Test*` class's
`test_*` methods and every module-level `test_*` function, resolves
fixtures/parametrize cases by calling the real fixture functions and
real parametrize value lists straight from each test file, calls each
resulting test invocation, and reports pass/fail counts — it only
replaces pytest's collection/reporting machinery, never anything about
what a test actually checks (see docs/phase-6-notes.md,
docs/evaluation-report.md, docs/release-report.md).

Usage: PYTHONPATH=backend:. python3 scripts/sandbox_verification/run_pure_tests_standalone.py
"""

import importlib
import inspect
import sys
import types
import traceback

# --- Minimal pytest shim ----------------------------------------------
# pytest itself isn't installed in this sandbox. The modules below use
# exactly four pytest features - `pytest.raises`, `pytest.approx`,
# `pytest.fixture`, and `pytest.mark.parametrize` - and nothing else
# (confirmed by grepping every included file for "pytest\."; no
# `monkeypatch`, no other builtin fixtures). Rather than skip these
# real assertions, this provides real, independent implementations of
# just those four well-defined utilities so the actual test logic
# still executes for real, unmodified. This does not touch what is
# being asserted.


class _RaisesContext:
    def __init__(self, expected_exception):
        self.expected_exception = expected_exception

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected_exception}")
        if not issubclass(exc_type, self.expected_exception):
            return False
        return True


class _Approx:
    def __init__(self, value, rel=1e-6, abs_tol=1e-12):
        self.value = value
        self.rel = rel
        self.abs_tol = abs_tol

    def __eq__(self, other):
        return abs(other - self.value) <= max(self.rel * abs(self.value), self.abs_tol)

    def __repr__(self):
        return f"approx({self.value!r})"


def _fixture(func):
    func._is_pytest_fixture = True
    return func


class Skipped(Exception):
    pass


def _importorskip(module_name):
    try:
        return importlib.import_module(module_name)
    except ImportError:
        raise Skipped(f"could not import {module_name!r}")


class _Mark:
    @staticmethod
    def parametrize(argnames, argvalues):
        names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)

        def decorator(func):
            func._pytest_parametrize = (names, list(argvalues))
            return func

        return decorator


_pytest_stub = types.ModuleType("pytest")
_pytest_stub.raises = _RaisesContext
_pytest_stub.approx = _Approx
_pytest_stub.fixture = _fixture
_pytest_stub.mark = _Mark
_pytest_stub.importorskip = _importorskip
_pytest_stub.skip = lambda msg="": (_ for _ in ()).throw(Skipped(msg))
_pytest_stub.Skipped = Skipped
sys.modules.setdefault("pytest", _pytest_stub)


def _resolve_fixture(module, name):
    """Call the module-level function decorated `@pytest.fixture` named
    `name`, with no arguments (every fixture in these files takes
    none)."""

    fixture_func = getattr(module, name, None)
    if fixture_func is None or not getattr(fixture_func, "_is_pytest_fixture", False):
        raise LookupError(f"no fixture named {name!r} in {module.__name__}")
    return fixture_func()


def _call_test(module, func):
    """Call a test function/method, resolving fixture and parametrize
    params by name against the module's own fixtures. Returns a list of
    (ok: bool, traceback_str_or_None) — one entry per invocation
    (parametrize expands one function into several)."""

    sig = inspect.signature(func)
    param_names = [p for p in sig.parameters if p != "self"]
    parametrize = getattr(func, "_pytest_parametrize", None)

    if parametrize is None:
        try:
            kwargs = {name: _resolve_fixture(module, name) for name in param_names}
            func(**kwargs)
            return [("passed", None)]
        except Skipped as exc:
            return [("skipped", str(exc))]
        except Exception:
            return [("failed", traceback.format_exc())]

    names, argvalues = parametrize
    results = []
    for values in argvalues:
        values = values if isinstance(values, tuple) else (values,)
        case_kwargs = dict(zip(names, values))
        try:
            for name in param_names:
                if name not in case_kwargs:
                    case_kwargs[name] = _resolve_fixture(module, name)
            func(**case_kwargs)
            results.append(("passed", None))
        except Skipped as exc:
            results.append(("skipped", str(exc)))
        except Exception:
            results.append(("failed", traceback.format_exc()))
    return results

MODULES = [
    "tests.test_evaluation_metrics",
    "tests.test_evaluation_dataset",
    "tests.test_prompt_injection",
    "tests.test_prompt",
    "tests.test_citations",
    "tests.test_validation",
    "tests.test_answer_generation",
    "tests.test_comparison",
    "tests.test_fusion",
    "tests.test_chunking",
    "tests.test_dedup",
    "tests.test_normalize",
    "tests.test_claude_client",
    "tests.test_clinicaltrials_client",
    "tests.test_pubmed_client",
    "tests.test_embeddings",
]

total_passed = 0
total_failed = 0
total_skipped = 0
failures = []
skips = []

def _run_module(mod_name):
    module = importlib.import_module(mod_name)
    print(f"=== {mod_name} ===")
    counts = {"passed": 0, "failed": 0, "skipped": 0}

    def _record(test_name, outcome, detail):
        counts[outcome] += 1
        if outcome == "skipped":
            skips.append((mod_name, test_name, detail))
        elif outcome == "failed":
            failures.append((mod_name, test_name, detail))

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and name.startswith("Test"):
            instance = obj()
            for method_name in dir(instance):
                if method_name.startswith("test_"):
                    method = getattr(instance, method_name)
                    for outcome, detail in _call_test(module, method):
                        _record(f"{name}.{method_name}", outcome, detail)
        elif (
            callable(obj)
            and name.startswith("test_")
            and getattr(obj, "__module__", "") == mod_name
        ):
            for outcome, detail in _call_test(module, obj):
                _record(name, outcome, detail)

    print(f"  {counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped")
    return counts


for mod_name in MODULES:
    sys.path.insert(0, ".")
    counts = _run_module(mod_name)
    total_passed += counts["passed"]
    total_failed += counts["failed"]
    total_skipped += counts["skipped"]

print()
print(f"TOTAL: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")
if skips:
    print()
    print("=== SKIPPED (matches real pytest.importorskip/pytest.skip semantics) ===")
    for mod_name, test_name, detail in skips:
        print(f"--- {mod_name}::{test_name} --- {detail}")
if failures:
    print()
    print("=== FAILURES ===")
    for mod_name, test_name, tb in failures:
        print(f"--- {mod_name}::{test_name} ---")
        print(tb)

sys.exit(1 if total_failed else 0)
