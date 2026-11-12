"""Shared Gemini client and model configuration."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from google import genai

from game_state import ROOT

load_dotenv(ROOT / ".env")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
