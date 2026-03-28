import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "alarm"
    / "scripts"
    / "operate_alert.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_operate_alert_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_payload(output: str):
    match = re.search(
        r"##ALARM_OPERATION_START##\s*(.*?)\s*##ALARM_OPERATION_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_main_maps_actions_and_emits_operation_block(monkeypatch):
    module = load_module()
    seen = []

    def fake_put_json(path, *, payload=None, params=None, timeout=30):
        seen.append((path, payload, params, timeout))
        return {"updated": len(payload["ids"])}

    monkeypatch.setattr(module, "put_json", fake_put_json)

    for action, expected_status in (
        ("mute", "ALERT_MUTED"),
        ("resolve", "ALERT_RESOLVED"),
        ("reopen", "ALERT_FIRING"),
    ):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = module.main(["alert-1", "--action", action])

        output = stdout.getvalue()
        payload = extract_payload(output)
        assert exit_code == 0
        assert "Updated 1 alert(s)." in output
        assert payload["action"] == action
        assert payload["status"] == expected_status
        assert payload["alert_ids"] == ["alert-1"]
        assert payload["request"]["status"] == expected_status

    assert [item[1]["status"] for item in seen] == [
        "ALERT_MUTED",
        "ALERT_RESOLVED",
        "ALERT_FIRING",
    ]


def test_main_serializes_batch_ids_into_request_payload(monkeypatch):
    module = load_module()
    captured = {}

    def fake_put_json(path, *, payload=None, params=None, timeout=30):
        captured["path"] = path
        captured["payload"] = payload
        return {"updated": len(payload["ids"])}

    monkeypatch.setattr(module, "put_json", fake_put_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1", "alert-2", "alert-3", "--action", "resolve"])

    output = stdout.getvalue()
    payload = extract_payload(output)
    assert exit_code == 0
    assert captured["path"] == "/alarm-alert/operation"
    assert captured["payload"] == {
        "ids": ["alert-1", "alert-2", "alert-3"],
        "status": "ALERT_RESOLVED",
    }
    assert payload["alert_ids"] == ["alert-1", "alert-2", "alert-3"]
    assert payload["request"] == captured["payload"]


def test_main_invalid_action_returns_non_zero_with_error():
    module = load_module()

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1", "--action", "acknowledge"])

    output = stdout.getvalue()
    assert exit_code != 0
    assert "[ERROR]" in output
    assert "Unsupported action" in output


def test_main_runtime_failure_returns_non_zero(monkeypatch):
    module = load_module()

    def fake_put_json(path, *, payload=None, params=None, timeout=30):
        raise RuntimeError("operation failed")

    monkeypatch.setattr(module, "put_json", fake_put_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1", "--action", "mute"])

    output = stdout.getvalue()
    assert exit_code != 0
    assert "[ERROR] operation failed" in output
