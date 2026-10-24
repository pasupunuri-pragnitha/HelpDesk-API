import logging
import os
from unittest import mock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_settings_default_values():
    """Test default values of Settings."""
    with mock.patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.PROJECT_NAME == "HelpDesk API"
        assert settings.VERSION == "0.1.0"
        assert settings.API_V1_STR == "/api/v1"
        assert "mysql+pymysql" in settings.DATABASE_URL
        assert settings.SECRET_KEY == "change-me"


def test_settings_custom_env_override():
    """Test that environment variables override defaults."""
    custom_db_url = "mysql+pymysql://user:pass@remote:3306/custom_db"
    custom_secret = "custom_secret_key_at_least_32_chars_long"
    with mock.patch.dict(os.environ, {"DATABASE_URL": custom_db_url, "SECRET_KEY": custom_secret}):
        custom_settings = Settings(_env_file=None)
        assert custom_settings.DATABASE_URL == custom_db_url
        assert custom_settings.SECRET_KEY == custom_secret


def test_startup_warning_when_placeholder_secret_used(caplog):
    """Test that startup logs a warning when the placeholder SECRET_KEY is used."""
    from app.core.config import settings

    original_secret = settings.SECRET_KEY
    try:
        settings.SECRET_KEY = "change-me"
        with caplog.at_level(logging.WARNING, logger="helpdesk_api"):
            with TestClient(app):
                pass
        warning_records = [rec for rec in caplog.records if "SECURITY WARNING" in rec.message]
        assert len(warning_records) >= 1
        # Crucial security check: the warning MUST NOT leak the key value
        assert "change-me" not in warning_records[0].message
        assert "SECRET_KEY is set to a placeholder" in warning_records[0].message
    finally:
        settings.SECRET_KEY = original_secret
