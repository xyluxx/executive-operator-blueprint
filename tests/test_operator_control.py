import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "operator-control"


def load_tools():
    spec = importlib.util.spec_from_file_location("operator_control_tools", PLUGIN / "tools.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_is_disabled_by_default_and_hook_is_only_defense_in_depth():
    manifest = yaml.safe_load((PLUGIN / "plugin.yaml").read_text())
    assert manifest["enabled"] is False
    assert "pre_tool_call" in manifest["hooks"]
    assert "defense-in-depth" in manifest["notes"]
    tools = load_tools()
    assert tools.pre_tool_call("operator_control_execute", {}, enabled=False)["allowed"] is False
    assert tools.pre_tool_call("terminal", {"command": "send"}, enabled=True)["allowed"] is False


def test_distribution_owns_plugin_and_pack_remains_optional():
    distribution = yaml.safe_load((ROOT / "distribution.yaml").read_text())
    packs = yaml.safe_load((ROOT / "optional-packs.yaml").read_text())["packs"]
    assert "plugins/" in distribution["distribution_owned"]
    assert packs["operator-control"]["default_enabled"] is False
    assert packs["operator-control"]["source"]["locator"] == "plugins/operator-control"


def test_model_facing_plugin_has_no_secret_reveal_surface():
    source = (PLUGIN / "tools.py").read_text().lower()
    for forbidden in ("get_plaintext", "recover-link", "recipient_url", "vault-link"):
        assert forbidden not in source


def test_plugin_manifest_declares_every_registered_tool_and_hook():
    manifest = yaml.safe_load((PLUGIN / "plugin.yaml").read_text())
    assert manifest["provides_tools"] == ["operator_control_execute"]
    assert manifest["provides_hooks"] == ["pre_tool_call"]


def test_model_plugin_has_no_admin_issuance_surface_and_admin_cli_exists():
    model_source = (PLUGIN / "__init__.py").read_text().lower()
    assert "issue_approval" not in model_source
    admin = ROOT / "scripts" / "operator_control_admin.py"
    assert admin.is_file()
    source = admin.read_text().lower()
    for command in ("policy", "approval", "evidence", "acceptance"):
        assert command in source
    assert "authenticate_admin" in source


def test_docs_scope_true_coverage_and_kanban_observer_limit():
    guardrails = (ROOT / "docs" / "06-guardrails-and-recovery.md").read_text().lower()
    integrations = (ROOT / "docs" / "11-native-integrations-and-extensions.md").read_text().lower()
    assert "observer-only" in guardrails
    assert "cannot veto" in guardrails
    assert "generic terminal" in guardrails and "generic browser" in guardrails
    assert "disabled by default" in integrations
    assert "authoritative" in integrations and "supported write" in integrations
