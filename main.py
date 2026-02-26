import logging
import os
import sys

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
    USE_MOCK = False # Set to False in production
    if USE_MOCK:
         logger.warning("Running in MOCK mode. Connecting algorithms but avoiding API costs.")

    try:
        fetcher = SensorTowerFetcher(use_mock=USE_MOCK)
        analyzer = VideoAnalyzer(use_mock=USE_MOCK)
        renderer = ReportRenderer(template_dir=os.path.join(os.path.dirname(__file__), 'templates'))
        
        # 2. Fetch Data (Step 2)
        logger.info("Step 2: Fetching Video Data...")
        top_videos_dict = fetcher.fetch_top_30_slg_videos()
        if not top_videos_dict or (not top_videos_dict.get('applovin') and not top_videos_dict.get('facebook')):
            logger.error("No videos retrieved. Exiting workflow.")
            sys.exit(1)
            
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
            monitored_apps=top_videos_dict.get('monitored_apps', [])
        )
        
        logger.info(f"Workflow Complete! Artifact generated at: {output_file_path}")

    except Exception as e:
        logger.exception(f"An error occurred during workflow execution: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
