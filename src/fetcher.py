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
            "kingshot", 
            "Whiteout Survival", 
            "Dark War:Survival", 
            "Lords Mobile: Kingdom wars", 
            "Last War:Survival", "Tiles Survive", 
            "Hero Wars: Alliance Fantasy", 
            "Evony", 
            "Fate War", 
            "Age of Empires Mobile",
            "Last Z: Survival Shooter",
            "Last Asylum",
            "TopHeroes",
        ]

    def fetch_top_30_slg_videos(self, cache_file: str = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches the top 30 SLG video ads from the last 7 days in the US, for Applovin and Facebook.
        If cache_file is provided and exists, it will load data from there to save API costs.
        """
        if cache_file and os.path.exists(cache_file):
            logger.info(f"💾 Found existing raw data cache at {cache_file}. Loading from cache to save API costs!")
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache from {cache_file}: {e}. Proceeding with API fetch.")

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
        # Calculate date range for the previous week (7 days ending the day before yesterday).
        # For example, if run on March 3rd, end_date is March 1st, start_date is Feb 23rd.
        now = datetime.now()
        end_date = now - timedelta(days=2)
        start_date = end_date - timedelta(days=6)
        
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
            "category": "6014", #Games
            "date": end_str,
            "period": "week",
            "limit": 250, # Maximize fetch to filter locally
            "page": 1
        }

        monitored_apps = {}
        results = {
            "applovin": self._fetch_top_for_network("Applovin", base_params, start_str, end_str, monitored_apps),
            "facebook": self._fetch_top_for_network("Facebook", base_params, start_str, end_str, monitored_apps),
            "youtube": self._fetch_top_for_network("Youtube", base_params, start_str, end_str, monitored_apps),
            "monitored_apps": list(monitored_apps.values())
        }
        
        logger.info(f"Successfully retrieved Applovin ({len(results['applovin'])}) and Facebook ({len(results['facebook'])}) real video records.")
        return results

    def _fetch_top_for_network(self, network_name: str, base_params: Dict[str, Any], start_str: str, end_str: str, monitored_apps: Dict[str, Dict[str, str]] = None) -> List[Dict[str, Any]]:
        top_endpoint = f"{self.base_url}/unified/ad_intel/creatives/top"
        params = base_params.copy()
        params["network"] = network_name
        
        target_ads = []
        seen_ad_ids = set()
        
        max_pages = 50 # Allow deep pagination since we are filtering from all categories
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
                    
                    # Try to get app_id for later share lookup
                    unified_app_id = app_info.get("app_id") or app_info.get("unified_app_id") or app_info.get("id")
                    
                    if video_url:
                        target_ads.append({
                            "ad_id": ad_id,
                            "app_id": unified_app_id,
                            "app_name": app_name, 
                            "ad_network": network_name,
                            "first_seen_at": unit.get("first_seen_at", "未知")[:10],
                            "last_seen_at": unit.get("last_seen_at", "未知")[:10],
                            "video_url": video_url,
                            "thumbnail_url": first_creative.get("preview_url") or first_creative.get("thumb_url", ""),
                            "duration_seconds": first_creative.get("video_duration", 0),
                            "share": 0 # Default, will be updated via second API call
                        })
            current_page += 1
            
        # Limit to top 30
        final_top = target_ads[:30]
        
        # Second API call to get the exact shares among target apps
        # We need the app_ids of the target apps
        target_app_ids = [
            "67bb93ed47b43a18952ffdfc", # Kingshot                    ok
            "638ee532480da915a62f0b34", # Whiteout Survival           ok
            "6573c39d5c3b423d5d04560f", # Dark War:Survival           ok
            "567a0aee0f1225ea0e006fe9", # Lords Mobile: Kingdom wars  ok
            "64075e77537c41636a8e1c58", # Last War:Survival           ok         
            "67d3aaff2c328ae8e547d0ef", # Tiles Survive               ok  
            "58a5031adcbd16685d00ba8f", # Hero Wars: Alliance Fantasy ok
            "658ea0be1fc48c4dbb3065e6", # Last Z: Survival Shooter    ok
            "5869720d0211a6180f000ebc", # Evony                       ok 
            "68411dcfc0b33b442b5f2320", # Fate War                    ok
            "65d5c34346b00723e5e77ebd", # Age of Empires Mobile       ok
            "698d49af6297762a8f53c7c2", # Last Asylum: Plague
            "63bd1e79e36abf4ca724dad2", # Top Heroes
        ]
        
        if target_app_ids:
            try:
                logger.info(f"Fetching share data for {len(target_app_ids)} target apps on {network_name}...")
                share_params = {
                    "auth_token": base_params.get("auth_token"),
                    "networks": network_name,
                    "app_ids": ",".join(target_app_ids),
                    "start_date": start_str,
                    "end_date": end_str,
                    "countries": base_params.get("country", "US"),
                    "os": base_params.get("os", "unified"),
                    "ad_types": base_params.get("ad_types", "video"),
                    "new_creative": base_params.get("new_creative", "false"),
                    "limit": 100
                }
                
                creatives_endpoint = f"{self.base_url}/unified/ad_intel/creatives"
                share_map = {}
                page = 1
                
                while True:
                    share_params["page"] = page
                    share_resp = requests.get(creatives_endpoint, params=share_params)
                    if share_resp.status_code == 200:
                        share_data = share_resp.json()
                        ad_units = share_data.get("ad_units", [])
                        
                        for unit in ad_units:
                            share_map[unit.get("id")] = unit.get("share", 0)
                            
                        if not ad_units or len(ad_units) < 100 or page >= 40:
                            break
                            
                        if all(ad["ad_id"] in share_map for ad in final_top):
                            break
                            
                        page += 1
                    else:
                        logger.error(f"Failed to fetch share data: {share_resp.status_code} - {share_resp.text}")
                        break
                        
                # Update shares in our final_top list
                for video in final_top:
                    raw_share = share_map.get(video["ad_id"])
                    if raw_share is None:
                        video["share"] = "无数据"
                    elif isinstance(raw_share, (int, float)):
                        formatted_share = f"{raw_share * 100:.2f}%"
                        if formatted_share == "0.00%":
                            video["share"] = "<0.01%"
                        else:
                            video["share"] = formatted_share
                    else:
                        video["share"] = str(raw_share)
            except Exception as e:
                logger.error(f"Exception during share fetch: {e}")
                    
        # Finalize ranks
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
                     "ad_id": f"AD_ID_{i:04d}",
                     "share": f"{random.uniform(0.01, 0.3) * 100:.2f}%"
                 })
             return mock_data
             
        return {
             "applovin": make_list("Applovin"),
             "facebook": make_list("Facebook"),
             "youtube": make_list("Youtube")
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fetcher = SensorTowerFetcher(use_mock=True) # default to mock for direct file run testing
    data = fetcher.fetch_top_30_slg_videos()
    print(json.dumps(data[:2], indent=2, ensure_ascii=False)) # Print first 2 for preview
