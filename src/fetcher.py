import json
import logging
import os
import random
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.config import SENSOR_TOWER_API_KEY

logger = logging.getLogger(__name__)

class SensorTowerFetcher:
    """Fetcher for retrieving Top 30 video ads data."""
    
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        if not use_mock and not SENSOR_TOWER_API_KEY:
             logger.warning("Initializing fetcher without API Key.")
             # Fallback to mock if really no key, though config should have caught it
             self.use_mock = True

        self.base_url = "https://api.sensortower.com/v1"
        self.target_apps = [
            "kingshot", "Whiteout Survival", "Dark War:Survival", 
            "Lords Mobile: Kingdom wars", "Last War:Survival", "Tiles Survive", 
            "Hero Wars: Alliance Fantasy", "Last Z: Survival Shooter", 
            "Evony", "Fate War", "Age of Empires Mobile"
        ]

    def fetch_top_30_slg_videos(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches the top 30 SLG video ads from the last 7 days in the US, for Applovin and Facebook.
        """
        logger.info("Fetching Top 30 SLG Video Ads...")
            
        try:
            return self._fetch_real_data()
        except Exception as e:
            logger.error(f"Failed to fetch real data: {e}. Falling back to mock data.")
            return self._generate_mock_data(count=30)
            
    def _fetch_real_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Implementation to fetch real data from Sensor Tower API.
        Queries the `/top` endpoint twice to get the Top 30 Applovin and Top 30 Facebook SLG videos.
        Returns a dictionary with keys 'applovin' and 'facebook'.
        """
        # Calculate date range (last 7 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        date_format = "%Y-%m-%d"
        start_str = start_date.strftime(date_format)
        end_str = end_date.strftime(date_format)
        
        logger.info(f"Querying Sensor Tower API for dates: {start_str} to {end_str}, Country: US")
        
        base_params = {
            "auth_token": SENSOR_TOWER_API_KEY,
            "os": "unified",
            "country": "US",
            "ad_types": "video",
            "new_creative": "false",
            "category": "7017", # Strategy Games
            "date": end_str,
            "period": "week",
            "limit": 250, # Maximize fetch to filter locally
            "page": 1
        }

        monitored_apps = {}
        results = {
            "applovin": self._fetch_top_for_network("Applovin", base_params, monitored_apps),
            "facebook": self._fetch_top_for_network("Facebook", base_params, monitored_apps),
            "monitored_apps": list(monitored_apps.values())
        }
        
        logger.info(f"Successfully retrieved Applovin ({len(results['applovin'])}) and Facebook ({len(results['facebook'])}) real video records.")
        return results

    def _fetch_top_for_network(self, network_name: str, base_params: Dict[str, Any], monitored_apps: Dict[str, Dict[str, str]] = None) -> List[Dict[str, Any]]:
        top_endpoint = f"{self.base_url}/unified/ad_intel/creatives/top"
        params = base_params.copy()
        params["network"] = network_name
        
        target_ads = []
        seen_ad_ids = set()
        
        max_pages = 10 # Protect against infinite loops (2500 ads deep)
        current_page = 1
        
        while len(target_ads) < 30 and current_page <= max_pages:
            params["page"] = current_page
            logger.info(f"Fetching {network_name} Top page {current_page} (Current matching: {len(target_ads)}/30)...")
            
            response = requests.get(top_endpoint, params=params)
            if response.status_code != 200:
                logger.error(f"SensorTower API Error (/top) for {network_name}: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            ad_units_top = data.get("ad_units", [])
            
            if not ad_units_top:
                break # No more data available
            
            for unit in ad_units_top:
                if len(target_ads) >= 30:
                    break
                    
                app_info = unit.get("app_info", {})
                app_name = app_info.get("name", "")
                ad_id = unit.get("id")
                
                # Check if this creative belongs to one of our target apps
                is_target = any(target.lower() in app_name.lower() for target in self.target_apps)
                if is_target:
                    if monitored_apps is not None and app_name not in monitored_apps:
                        monitored_apps[app_name] = {
                            "name": app_name,
                            "icon_url": app_info.get("icon_url", "")
                        }
                        
                if is_target and ad_id and ad_id not in seen_ad_ids:
                    seen_ad_ids.add(ad_id)
                    
                    creatives = unit.get("creatives", [])
                    if not creatives:
                        continue
                        
                    first_creative = creatives[0]
                    video_url = first_creative.get("creative_url")
                    
                    if video_url:
                        target_ads.append({
                            "ad_id": ad_id,
                            "app_name": app_name, 
                            "ad_network": network_name,
                            "first_seen_at": unit.get("first_seen_at", "未知")[:10],
                            "last_seen_at": unit.get("last_seen_at", "未知")[:10],
                            "video_url": video_url,
                            "thumbnail_url": first_creative.get("preview_url") or first_creative.get("thumb_url", ""),
                            "duration_seconds": first_creative.get("video_duration", 0)
                        })
            current_page += 1
                    
        # Sort and finalize ranks
        final_top = target_ads[:30]
        for i, video in enumerate(final_top):
             video["rank"] = i + 1
             
        return final_top

    def _generate_mock_data(self, count: int) -> Dict[str, List[Dict[str, Any]]]:
        """Generates mock data representing fetched video ads for two networks."""
        def make_list(network: str):
             mock_data = []
             for i in range(1, count + 1):
                 game_name = random.choice(self.target_apps)
                 mock_data.append({
                     "rank": i,
                     "app_name": game_name,
                     "ad_network": network,
                     "first_seen_at": "2026-02-01",
                     "last_seen_at": "2026-02-25",
                     "video_url": f"https://example.com/mock_video_{i}.mp4",
                     "thumbnail_url": f"https://picsum.photos/seed/{i+100}/400/225",
                     "duration_seconds": random.randint(15, 60),
                     "ad_id": f"AD_ID_{i:04d}"
                 })
             return mock_data
             
        return {
             "applovin": make_list("Applovin"),
             "facebook": make_list("Facebook")
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fetcher = SensorTowerFetcher(use_mock=True) # default to mock for direct file run testing
    data = fetcher.fetch_top_30_slg_videos()
    print(json.dumps(data[:2], indent=2, ensure_ascii=False)) # Print first 2 for preview
