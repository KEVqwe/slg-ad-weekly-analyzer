import logging
import os
import sys
import json
from datetime import datetime

from src.fetcher import SensorTowerFetcher
from src.analyzer import VideoAnalyzer
from src.renderer import ReportRenderer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Weekly US SLG Top30 Video Ads Analysis Workflow...")
    
    # 1. Initialize Components (Using False for actual run, True for testing)
    USE_MOCK = False# Set to False in production
    if USE_MOCK:
         logger.warning("Running in MOCK mode. Connecting algorithms but avoiding API costs.")

    try:
        # Generate week-based archive directory
        year, week, _ = datetime.now().isocalendar()
        archive_dir_name = f"{year}_W{week:02d}"
        archive_dir_path = os.path.join("archive", archive_dir_name)
        
        # Ensure the archive directory exists
        os.makedirs(archive_dir_path, exist_ok=True)
        
        # Define paths for outputs
        cache_filepath = os.path.join(archive_dir_path, "analysis_cache.json")
        raw_data_filepath = os.path.join(archive_dir_path, "raw_sensortower_data.json")
        report_filepath = os.path.join(archive_dir_path, f"{archive_dir_name}_weekly_report.html")
        
        # Clean up legacy cache file if it exists in root
        legacy_cache = "analysis_cache.json"
        if os.path.exists(legacy_cache):
            try:
                os.remove(legacy_cache)
                logger.info(f"Removed legacy root cache file: {legacy_cache}")
            except Exception:
                pass

        fetcher = SensorTowerFetcher(use_mock=USE_MOCK)
        analyzer = VideoAnalyzer(use_mock=USE_MOCK, cache_file=cache_filepath)
        renderer = ReportRenderer(template_dir=os.path.join(os.path.dirname(__file__), 'templates'))
        
        # 2. Fetch Data (Step 2)
        logger.info("Step 2: Fetching Video Data...")
        top_videos_dict = fetcher.fetch_top_30_slg_videos()
        if not top_videos_dict or (not top_videos_dict.get('applovin') and not top_videos_dict.get('facebook')):
            logger.error("No videos retrieved. Exiting workflow.")
            sys.exit(1)
            
        # Archive the raw SensorTower data
        try:
            with open(raw_data_filepath, 'w', encoding='utf-8') as f:
                json.dump(top_videos_dict, f, ensure_ascii=False, indent=2)
            logger.info(f"Raw data archived to {raw_data_filepath}")
        except Exception as e:
            logger.warning(f"Failed to archive raw data to {raw_data_filepath}: {e}")
            
        # 3. Analyze Videos (Step 3) 
        logger.info("Step 3: Analyzing Videos structurally via GenAI and Comparing Ranks...")
        
        # Helper: Extract week number and sort descending to find previous week
        def get_all_week_archives():
            if not os.path.exists("archive"):
                return []
            dirs = [d for d in os.listdir("archive") if os.path.isdir(os.path.join("archive", d)) and "_W" in d]
            dirs.sort(reverse=True) # e.g. ["2024_W45", "2024_W44", "2023_W52"]
            return dirs
            
        previous_week_ranks = {}
        all_archives = get_all_week_archives()
        # Find the most recent archive that is NOT the current week
        prev_archive_dir = None
        for d in all_archives:
            if d != archive_dir_name:
                prev_archive_dir = d
                break
                
        if prev_archive_dir:
            logger.info(f"Cross-referencing ranks with previous week: {prev_archive_dir}")
            prev_data_path = os.path.join("archive", prev_archive_dir, "raw_sensortower_data.json")
            if os.path.exists(prev_data_path):
                try:
                    with open(prev_data_path, 'r', encoding='utf-8') as f:
                        prev_data = json.load(f)
                        for network in ['applovin', 'facebook']:
                            for item in prev_data.get(network, []):
                                previous_week_ranks[item['ad_id']] = item['rank']
                except Exception as e:
                    logger.warning(f"Failed to load previous week data: {e}")
        else:
            logger.info("No previous week archive found for rank comparison.")
            
        def calculate_rank_change(video: dict):
            ad_id = video.get('ad_id')
            current_rank = video.get('rank')
            if ad_id in previous_week_ranks:
                prev_rank = previous_week_ranks[ad_id]
                change = prev_rank - current_rank # e.g. prev 5, current 3 -> +2 (up)
                video['rank_change'] = change
                video['rank_trend'] = "up" if change > 0 else ("down" if change < 0 else "same")
            else:
                video['rank_change'] = "NEW"
                video['rank_trend'] = "new"
        
        applovin_videos = top_videos_dict.get('applovin', [])
        for v in applovin_videos: 
            v['channel'] = 'applovin'
            calculate_rank_change(v)
                 
        facebook_videos = top_videos_dict.get('facebook', [])
        for v in facebook_videos: 
            v['channel'] = 'facebook'
            calculate_rank_change(v)
        
        all_videos = applovin_videos + facebook_videos
        logger.info(f"--- Analyzing All {len(all_videos)} Videos Concurrently ---")
        
        # Max concurrency for pay-as-you-go. Run all concurrently!
        analyzed_all = analyzer.analyze_videos_concurrently(all_videos, max_workers=15)
        
        analyzed_applovin = [v for v in analyzed_all if v.get('channel') == 'applovin']
        analyzed_facebook = [v for v in analyzed_all if v.get('channel') == 'facebook']
                 
        # 4. Strategic Summary (Step 4)
        logger.info("Step 4: Generating Strategic Summary...")
        strategic_report = analyzer.generate_strategy_summary(analyzed_applovin, analyzed_facebook)
        strategy_data = strategic_report.get("strategy_summary", {})
        
        # 5. Render HTML (Step 5)
        logger.info("Step 5: Synthesizing HTML Report...")
        output_file_path = renderer.render(
            strategy_summary=strategy_data,
            applovin_items=analyzed_applovin,
            facebook_items=analyzed_facebook,
            monitored_apps=top_videos_dict.get('monitored_apps', []),
            output_path=report_filepath
        )
        
        # Write outputs to GitHub Actions environment if available
        github_env = os.getenv('GITHUB_ENV')
        if github_env:
            with open(github_env, 'a', encoding='utf-8') as f:
                f.write(f"REPORT_WEEK={archive_dir_name}\n")
                f.write(f"REPORT_HTML_PATH={output_file_path}\n")
        
        logger.info(f"Workflow Complete! Artifact generated at: {output_file_path}")

    except Exception as e:
        logger.exception(f"An error occurred during workflow execution: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
