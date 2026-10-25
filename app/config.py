from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://soccer.highlightly.net"


def get_settings() -> Settings:
    key = os.getenv("HIGHLIGHTLY_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "HIGHLIGHTLY_API_KEY is missing. Add it as a GitHub Actions repository "
            "secret; do not paste it into source code or commit it to GitHub."
        )
    base_url = os.getenv(
        "HIGHLIGHTLY_API_BASE_URL", "https://soccer.highlightly.net"
    ).strip().rstrip("/")
    return Settings(api_key=key, base_url=base_url)
