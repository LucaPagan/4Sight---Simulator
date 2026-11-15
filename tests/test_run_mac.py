import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("port", [3000, 8000])
def test_run_mac_rejects_busy_ports_before_starting(tmp_path, port):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(Path(__file__).parents[1] / "scripts/run_mac.sh", scripts / "run_mac.sh")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    probe = binaries / "lsof"
    probe.write_text(f'#!/bin/bash\nif [[ "$*" == *":{port}"* ]]; then echo {os.getpid()}; else exit 1; fi\n')
    probe.chmod(0o755)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/bash\ntouch started\n")
    python.chmod(0o755)
    result = subprocess.run(
        ["bash", str(scripts / "run_mac.sh"), "qwen2.5:0.5b"],
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert str(port) in result.stderr
    assert "started" not in result.stdout
    assert not (tmp_path / "started").exists()


@pytest.mark.parametrize(
    ("args", "configured", "expected"),
    [
        ([], "qwen3.5:4b", "qwen3.5:4b"),
        (["qwen2.5:0.5b"], "qwen3.5:4b", "qwen2.5:0.5b"),
        ([], "", "qwen2.5:0.5b"),
    ],
)
def test_run_mac_model_precedence(tmp_path, args, configured, expected):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(Path(__file__).parents[1] / "scripts/run_mac.sh", scripts / "run_mac.sh")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in [("lsof", "exit 1"), ("npm", "exit 0"), ("curl", "exit 0")]:
        executable = binaries / name
        executable.write_text(f"#!/bin/bash\n{body}\n")
        executable.chmod(0o755)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/bash\nprintf "%s" "$AUDIENCE_OLLAMA_MODEL" > model.txt\n')
    python.chmod(0o755)
    result = subprocess.run(
        ["bash", str(scripts / "run_mac.sh"), *args],
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}", "AUDIENCE_OLLAMA_MODEL": configured},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "model.txt").read_text() == expected


def test_run_mac_restarts_its_previous_backend(tmp_path):
    import sys
    import threading

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(Path(__file__).parents[1] / "scripts/run_mac.sh", scripts / "run_mac.sh")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    old = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "-m", "audience_simulator.cli", "serve"],
        cwd=tmp_path,
    )
    reaper = threading.Thread(target=old.wait)
    reaper.start()
    real_lsof = shutil.which("lsof")
    probe = binaries / "lsof"
    probe.write_text(
        f'#!/bin/bash\nif [[ "$*" == *"-d cwd"* ]]; then exec "{real_lsof}" "$@"; fi\n'
        f'if [[ "$*" == *":8000"* ]] && kill -0 {old.pid} 2>/dev/null; then echo {old.pid}; else exit 1; fi\n'
    )
    probe.chmod(0o755)
    for name in ["npm", "curl"]:
        executable = binaries / name
        executable.write_text("#!/bin/bash\nexit 0\n")
        executable.chmod(0o755)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/bash\nprintf "%s" "$AUDIENCE_OLLAMA_MODEL" > model.txt\n')
    python.chmod(0o755)
    try:
        result = subprocess.run(
            ["bash", str(scripts / "run_mac.sh"), "qwen2.5:0.5b"],
            env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert old.poll() is not None
        assert (tmp_path / "model.txt").read_text() == "qwen2.5:0.5b"
    finally:
        if old.poll() is None:
            old.terminate()
        reaper.join(timeout=5)
