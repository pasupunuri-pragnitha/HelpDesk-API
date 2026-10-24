import os
from unittest import mock

from app.core.config import Settings


def test_settings_default_values():
    """Test default values of Settings."""
    settings = Settings()
    assert settings.PROJECT_NAME == "HelpDesk API"
    assert settings.VERSION == "0.1.0"
    assert settings.API_V1_STR == "/api/v1"
    assert "mysql+pymysql" in settings.DATABASE_URL


def test_settings_custom_env_override():
    """Test that environment variables override defaults."""
    custom_db_url = "mysql+pymysql://user:pass@remote:3306/custom_db"
    with mock.patch.dict(os.environ, {"DATABASE_URL": custom_db_url}):
        custom_settings = Settings()
        assert custom_settings.DATABASE_URL == custom_db_url
