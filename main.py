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
        logger.info("Step 3: Analyzing Videos structurally via GenAI...")
        
        applovin_videos = top_videos_dict.get('applovin', [])
        for v in applovin_videos: v['channel'] = 'applovin'
                 
        facebook_videos = top_videos_dict.get('facebook', [])
        for v in facebook_videos: v['channel'] = 'facebook'
        
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
        
        logger.info(f"Workflow Complete! Artifact generated at: {output_file_path}")

    except Exception as e:
        logger.exception(f"An error occurred during workflow execution: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
