from __future__ import annotations

import pytest

from agentgate.config import Config, find_pyproject, load_config
from agentgate.exceptions import ConfigError


def test_defaults_when_no_pyproject(tmp_path) -> None:
    config = load_config(tmp_path)
    assert config.trace_dir.name == "traces"
    assert config.strict is True
    assert config.policy.tool_sequence is True


def test_reads_configuration(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.agentgate]",
                'trace_dir = "golden"',
                "strict = false",
                'redact_keys = ["customer_email"]',
                "",
                "[tool.agentgate.policy]",
                "max_cost_usd = 0.05",
                'forbidden_tools = ["delete_customer"]',
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path)

    assert config.trace_dir.name == "golden"
    assert config.strict is False
    assert config.redact_keys == ["customer_email"]
    assert config.policy.max_cost_usd == 0.05
    assert config.policy.forbidden_tools == ["delete_customer"]


def test_pyproject_without_agentgate_section(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert load_config(tmp_path).trace_dir.name == "traces"


def test_invalid_configuration_is_rejected(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.agentgate]\nstrict = "absolutely"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="invalid"):
        load_config(tmp_path)


def test_unparseable_toml_is_rejected(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.agentgate\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="could not parse"):
        load_config(tmp_path)


def test_search_walks_upwards(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.agentgate]\n", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    found = find_pyproject(nested)
    assert found is not None and found.parent == tmp_path.resolve()


def test_trace_path_helper() -> None:
    assert Config().trace_path("refund").name == "refund.json"
