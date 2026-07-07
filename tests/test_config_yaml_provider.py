from __future__ import annotations

import yaml

import server


def _read_config(path):
    with path.open() as f:
        return yaml.safe_load(f)


def test_gpt55_startup_pins_codex_provider_even_when_api_keys_exist(tmp_path, monkeypatch) -> None:
    """API-key presence must not make Hermes route gpt-5.5 through OpenRouter auto."""
    monkeypatch.setattr(server, "HERMES_HOME", str(tmp_path))

    server.write_config_yaml(
        {
            "LLM_MODEL": "gpt-5.5",
            "OPENROUTER_API_KEY": "redacted",
            "NVIDIA_API_KEY": "redacted",
        }
    )

    config = _read_config(tmp_path / "config.yaml")
    assert config["model"] == {"default": "gpt-5.5", "provider": "openai-codex"}


def test_non_gpt55_api_key_model_still_uses_auto_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "HERMES_HOME", str(tmp_path))

    server.write_config_yaml(
        {
            "LLM_MODEL": "anthropic/claude-haiku-4-5",
            "ANTHROPIC_API_KEY": "redacted",
        }
    )

    config = _read_config(tmp_path / "config.yaml")
    assert config["model"] == {"default": "anthropic/claude-haiku-4-5", "provider": "auto"}
