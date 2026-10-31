"""Exercise the no-host CLI against real fixture setup and teardown."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _project(tmp_path: Path, conftest: str, tests: str) -> Path:
    test_dir = tmp_path / "project" / "tests"
    test_dir.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("run_logic_tests.py"), test_dir / "run_logic_tests.py")
    (test_dir / "pytest.ini").write_text("[pytest]\ntestpaths = .\n", encoding="utf-8")
    (test_dir / "conftest.py").write_text(conftest, encoding="utf-8")
    (test_dir / "test_fixtures.py").write_text(tests, encoding="utf-8")
    return test_dir


def _run(test_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONIOENCODING="utf-8")
    env.pop("WT_RUNNER_LEAK", None)
    return subprocess.run([sys.executable, str(test_dir / "run_logic_tests.py"), *args],
                          cwd=test_dir.parent.parent, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=30)


def test_logic_runner_supports_fixtures_parametrization_and_isolation(tmp_path):
    test_dir = _project(tmp_path, '''
import os
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def isolation():
    assert "WT_RUNNER_LEAK" not in os.environ
    yield
    with Path(__file__).with_name("teardown.txt").open("a") as f:
        f.write("done\\n")

@pytest.fixture
def dependent(request, tmp_path_factory):
    assert request.node.name.startswith("test_")
    return tmp_path_factory.mktemp("dependent")
''', '''
import pytest

@pytest.mark.parametrize("value", [1, 2])
def test_fixtures(monkeypatch, tmp_path, capsys, dependent, value):
    monkeypatch.setenv("WT_RUNNER_LEAK", str(value))
    (tmp_path / "sample").write_text(str(value))
    assert dependent.is_dir()
    print(value)
    assert capsys.readouterr().out.strip() == str(value)

@pytest.mark.skip(reason="must be skipped rather than invoked")
def test_skipped():
    raise AssertionError("skip was ignored")
''')
    result = _run(test_dir)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed, 1 skipped" in result.stdout
    assert (test_dir / "teardown.txt").read_text().splitlines() == ["done", "done"]


def test_logic_runner_propagates_failure_and_executes_finalizer(tmp_path):
    test_dir = _project(tmp_path, '''
from pathlib import Path
import pytest

@pytest.fixture
def cleanup(request):
    request.addfinalizer(lambda: Path(__file__).with_name("cleaned").write_text("yes"))
''', '''
def test_failure(cleanup):
    assert False, "intentional failure"
''')
    result = _run(test_dir)
    assert result.returncode == 1
    assert "1 failed" in result.stdout
    assert (test_dir / "cleaned").read_text() == "yes"


def test_logic_runner_forwards_pytest_selection_options(tmp_path):
    test_dir = _project(tmp_path, "", '''
def test_selected():
    pass

def test_other():
    assert False
''')
    result = _run(test_dir, "-k", "selected")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed, 1 deselected" in result.stdout
