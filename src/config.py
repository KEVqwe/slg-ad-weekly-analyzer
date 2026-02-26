import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SENSOR_TOWER_API_KEY = os.getenv("SENSOR_TOWER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REPORT_OUTPUT_DIR = os.getenv("REPORT_OUTPUT_DIR", "reports")

# Validate critical API keys (you can disable this during initial local testing without keys)
if not SENSOR_TOWER_API_KEY:
    print("WARNING: SENSOR_TOWER_API_KEY is not set in the environment.")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not set in the environment.")

# Ensure output directory exists
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
