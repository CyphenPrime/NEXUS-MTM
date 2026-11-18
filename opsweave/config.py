import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file (check local dir and file parent dir)
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

# Model and provider configurations
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip()
API_KEY = os.getenv("LLM_API_KEY", "").strip()
MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite").strip()
BASE_URL = os.getenv("LLM_BASE_URL", "").strip()

# Planning defaults, not pack facts
OPENING_MIN = 15   # planning default, not pack facts
LUNCH_MIN = 30     # planning default, not pack facts
CLOSING_MIN = 15   # planning default, not pack facts

# Operational limits and timeouts (seconds)
FULL_RUN_TIMEOUT_S = 110
UPDATE_TIMEOUT_S = 55
MAX_OUTPUT_TOKENS = 1500
REQUEST_TIMEOUT_S = 40
