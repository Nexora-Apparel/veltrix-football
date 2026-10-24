from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://api.football-data.org/v4"


def get_settings() -> Settings:
    key = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not key:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN is missing. Add it as a GitHub Actions repository "
            "secret; do not paste it into source code or commit it to GitHub."
        )
    base_url = os.getenv(
        "FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4"
    ).strip().rstrip("/")
    return Settings(api_key=key, base_url=base_url)
