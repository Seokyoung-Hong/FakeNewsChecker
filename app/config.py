import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
HIVE_API_KEY = os.getenv("HIVE_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")