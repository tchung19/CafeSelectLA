"""
CafeSelect — Pipeline Configuration
=====================================
Loads API keys from .env. Searches Workspace/, repo root, and
pre_build_validation/ in order so the same code works during development
(keys in pre_build_validation/) and in production (keys at repo root).
"""

import os
from pathlib import Path

_HERE = Path(__file__).parent

_ENV_CANDIDATES = [
    _HERE.parent / ".env",                              # Workspace/.env
    _HERE.parent.parent / ".env",                       # repo root .env
    _HERE.parent.parent / "pre_build_validation" / ".env",  # dev fallback
]

for _env_path in _ENV_CANDIDATES:
    if _env_path.exists():
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k not in os.environ:
                    os.environ[_k] = _v
        break

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
OPENAI_API_KEY        = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL          = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY          = os.environ.get("SUPABASE_KEY", "")


def require(name: str, value: str) -> str:
    if not value:
        raise EnvironmentError(f"{name} is not set. Add it to .env")
    return value
