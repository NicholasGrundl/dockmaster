"""Tests for UIConfig loading — covers edge cases in load_ui_config()."""

import json

import pytest

from dockmaster.ui.config import UIConfig, load_ui_config


class TestUIConfigDefaults:
    def test_default_brand_name(self):
        config = UIConfig()
        assert config.brand_name == "Dockmaster"

    def test_default_colors(self):
        config = UIConfig()
        assert config.primary_color == "#1a73e8"
        assert config.accent_color == "#198754"

    def test_custom_values(self):
        config = UIConfig(brand_name="Acme Auth", primary_color="#ff0000")
        assert config.brand_name == "Acme Auth"
        assert config.primary_color == "#ff0000"


class TestLoadUIConfig:
    def test_none_path_returns_defaults(self):
        config = load_ui_config(None)
        assert config.brand_name == "Dockmaster"

    def test_empty_string_path_returns_defaults(self):
        config = load_ui_config("")
        assert config.brand_name == "Dockmaster"

    def test_nonexistent_file_returns_defaults(self, tmp_path):
        config = load_ui_config(str(tmp_path / "does-not-exist.json"))
        assert config.brand_name == "Dockmaster"

    def test_valid_json_file(self, tmp_path):
        config_file = tmp_path / "ui.json"
        config_file.write_text(
            json.dumps(
                {
                    "brand_name": "Custom Brand",
                    "primary_color": "#abcdef",
                }
            )
        )
        config = load_ui_config(str(config_file))
        assert config.brand_name == "Custom Brand"
        assert config.primary_color == "#abcdef"
        # Other fields remain defaults
        assert config.accent_color == "#198754"

    def test_invalid_json_returns_defaults(self, tmp_path):
        config_file = tmp_path / "bad.json"
        config_file.write_text("not valid json {{{")
        config = load_ui_config(str(config_file))
        assert config.brand_name == "Dockmaster"

    def test_partial_config_merges_with_defaults(self, tmp_path):
        config_file = tmp_path / "partial.json"
        config_file.write_text(json.dumps({"footer_text": "My Footer"}))
        config = load_ui_config(str(config_file))
        assert config.footer_text == "My Footer"
        assert config.brand_name == "Dockmaster"

    @pytest.mark.parametrize(
        "logo_url",
        [
            None,
            "/static/logo.png",
            "https://example.com/logo.svg",
        ],
    )
    def test_logo_url_variants(self, tmp_path, logo_url):
        config_file = tmp_path / "logo.json"
        data = {"logo_url": logo_url} if logo_url is not None else {}
        config_file.write_text(json.dumps(data))
        config = load_ui_config(str(config_file))
        assert config.logo_url == logo_url
