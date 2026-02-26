import os
import logging
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Any

from src.config import REPORT_OUTPUT_DIR

logger = logging.getLogger(__name__)

class ReportRenderer:
    """Renders the analyzed data into a static HTML report."""
    
    def __init__(self, template_dir: str = 'templates'):
        self.template_dir = template_dir
        self.env = Environment(loader=FileSystemLoader(self.template_dir))
        self.template = self.env.get_template('report_template.html')

    def render(self, strategy_summary: Dict[str, Any], applovin_items: List[Dict[str, Any]], facebook_items: List[Dict[str, Any]], monitored_apps: List[Dict[str, str]] = None) -> str:
        """
        Renders the HTML report.
        Args:
            strategy_summary: Dict containing hit_patterns, competitor_tactics, actionable_advice
            applovin_items: List of dicts from Applovin network
            facebook_items: List of dicts from Facebook network
            monitored_apps: List of dicts containing competitor names and icon URLs
        Returns:
            Absolute path to the generated HTML file.
        """
        logger.info("Rendering HTML report...")
        
        # Calculate date range (last 7 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        report_date = f"{start_date.strftime('%Y年%m月%d日')} - {end_date.strftime('%Y年%m月%d日')}"
        
        # Render the template
        html_content = self.template.render(
            report_date=report_date,
            strategy_summary=strategy_summary,
            applovin_items=applovin_items,
            facebook_items=facebook_items,
            monitored_apps=monitored_apps or []
        )
        
        # Determine output filename: YYMMDD_weekly_report.html
        filename_date = datetime.now().strftime("%y%m%d")
        filename = f"{filename_date}_weekly_report.html"
        output_path = os.path.join(REPORT_OUTPUT_DIR, filename)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Report successfully generated at: {output_path}")
        return output_path

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Test rendering with mock data
    from src.fetcher import SensorTowerFetcher
    from src.analyzer import VideoAnalyzer
    
    fetcher = SensorTowerFetcher(use_mock=True)
    videos = fetcher.fetch_top_30_slg_videos()
    
    analyzer = VideoAnalyzer(use_mock=True)
    analyzed_videos = [analyzer.analyze_single_video(v) for v in videos[:5]] # test with first 5
    summary = analyzer.generate_strategy_summary(analyzed_videos)
    
    renderer = ReportRenderer()
    renderer.render(summary.get("strategy_summary", {}), analyzed_videos)
