from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _literal_subprocess_args(call: ast.Call) -> list[str]:
    args: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            args.append(arg.value)
    return args


def test_managed_dashboard_launch_does_not_pass_removed_tui_flag() -> None:
    """Hermes v0.16 removed `hermes dashboard --tui`; chat is always enabled."""
    tree = ast.parse((ROOT / "server.py").read_text())

    dashboard_launches = [
        _literal_subprocess_args(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_subprocess_exec"
        and _literal_subprocess_args(node)[:2] == ["hermes", "dashboard"]
    ]

    assert dashboard_launches, "expected a managed hermes dashboard launch"
    for launch_args in dashboard_launches:
        assert "--tui" not in launch_args
        assert "--skip-build" in launch_args


def test_watchdog_dashboard_launch_does_not_pass_removed_tui_flag() -> None:
    start_sh = (ROOT / "start.sh").read_text()
    launch_lines = [
        line.strip()
        for line in start_sh.splitlines()
        if line.strip().startswith("nohup hermes dashboard ")
    ]

    assert launch_lines, "expected a watchdog hermes dashboard launch"
    for line in launch_lines:
        assert "--tui" not in line
        assert "--no-open" in line
