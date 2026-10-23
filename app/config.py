from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://v3.football.api-sports.io"

def get_settings() -> Settings:
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "API_FOOTBALL_KEY is missing. Set it as an environment variable; "
            "do not paste it into source code or commit it to GitHub."
        )
    base_url = os.getenv(
        "API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io"
    ).strip().rstrip("/")
    return Settings(api_key=key, base_url=base_url)
