from datetime import time
from typing import Any
import zoneinfo
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    PROJECT_NAME: str = "HelpDesk API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "mysql+pymysql://helpdesk:helpdesk_password@localhost:3306/helpdesk_db"

    # JWT Authentication settings (placeholder by default; override in production via .env)
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Application logging level
    LOG_LEVEL: str = "INFO"

    # Business-Hours SLA Settings
    WORK_TIMEZONE: str = "Asia/Kolkata"
    WORK_DAY_START: str = "09:00"
    WORK_DAY_END: str = "18:00"
    WORK_DAYS: list[int] = [0, 1, 2, 3, 4]  # Monday=0 to Friday=4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("WORK_DAYS", mode="before")
    @classmethod
    def parse_work_days(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                return json.loads(v_str)
            return [int(x.strip()) for x in v_str.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def validate_business_hours_config(self) -> "Settings":
        # 1. Valid timezone
        try:
            zoneinfo.ZoneInfo(self.WORK_TIMEZONE)
        except Exception as exc:
            raise ValueError(f"Invalid WORK_TIMEZONE '{self.WORK_TIMEZONE}': {exc}") from exc

        # 2. Valid work days (at least one working day, days between 0 and 6)
        if not self.WORK_DAYS:
            raise ValueError("WORK_DAYS must contain at least one working day (0=Monday to 6=Sunday).")
        for day in self.WORK_DAYS:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError(f"Invalid weekday '{day}' in WORK_DAYS. Must be integer between 0 and 6.")

        # 3. Work start and end times format and start before end
        try:
            start_parts = [int(p) for p in self.WORK_DAY_START.split(":")]
            end_parts = [int(p) for p in self.WORK_DAY_END.split(":")]
            if len(start_parts) != 2 or len(end_parts) != 2:
                raise ValueError("Format must be HH:MM")
            start_t = time(start_parts[0], start_parts[1])
            end_t = time(end_parts[0], end_parts[1])
        except Exception as exc:
            raise ValueError(f"WORK_DAY_START and WORK_DAY_END must be 'HH:MM': {exc}") from exc

        if start_t >= end_t:
            raise ValueError(
                f"WORK_DAY_START ({self.WORK_DAY_START}) must be strictly before WORK_DAY_END ({self.WORK_DAY_END})."
            )

        return self


settings = Settings()

