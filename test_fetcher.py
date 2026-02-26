import os
import json
import logging
from dotenv import load_dotenv
from src.fetcher import SensorTowerFetcher

# Configure basic logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_fetcher():
    """
    A standalone script to test the SensorTower API fetcher.
    It prints out the raw JSON items and the final parsed targets
    so you can easily debug the API parameters and response structure.
    """
    print("=========================================")
    print("   Sensor Tower API Fetcher Test Script  ")
    print("=========================================\n")
    
    # 1. Load environment variables
    load_dotenv()
    api_key = os.getenv("SENSOR_TOWER_API_KEY")
    if not api_key:
        logger.error("SENSOR_TOWER_API_KEY not found in .env file! Please add it first.")
        return

    # 2. Initialize the Fetcher with MOCK turned OFF
    print("[*] Initializing VideoFetcher (MOCK = False)...")
    fetcher = SensorTowerFetcher(use_mock=False)
    
    # 3. Fetch Data
    print("[*] Calling API Endpoint: /unified/ad_intel/creatives/top...")
    try:
        # Call the private real data method to bypass mock checks and get exactly what is parsed
        top_videos_dict = fetcher._fetch_real_data()
        
        print("\n[*] Fetch Successful!")
        print(f"[*] Retrieved {len(top_videos_dict.get('applovin', []))} Applovin records and {len(top_videos_dict.get('facebook', []))} Facebook records.")
        print("------------- Parsed Output Preview -------------")
        
        print("\n------------- Top 10 Applovin JSON Output -------------")
        print(json.dumps(top_videos_dict.get("applovin", [])[:10], indent=2, ensure_ascii=False))

        print("\n------------- Top 10 Facebook JSON Output -------------")
        print(json.dumps(top_videos_dict.get("facebook", [])[:10], indent=2, ensure_ascii=False))

    except Exception as e:
        logger.error(f"Test Failed with Exception: {e}")
        print("\n[!] Please check your parameters in `src/fetcher.py` (_fetch_real_data).")

if __name__ == "__main__":
    test_fetcher()
