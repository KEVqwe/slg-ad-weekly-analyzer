import logging
import json
import os
import time
import requests
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel
from src.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# --- Pydantic Models for Structured Output ---
class VideoAnalysisResult(BaseModel):
    hook_design: str
    emotional_appeal: str
    content_structure: str
    wow_factor: str
    copywriting_features: str

class StrategySummaryResult(BaseModel):
    hit_patterns: str
    competitor_tactics: str
    actionable_advice: str


class VideoAnalyzer:
    """Handles interaction with Google GenAI for video analysis and summarization."""
    
    def __init__(self, use_mock: bool = False, cache_file: str = "analysis_cache.json"):
        self.use_mock = use_mock
        self.cache_file = cache_file
        self.analysis_cache = self._load_cache()
        self.cache_lock = threading.Lock()
        self.last_api_call_time = 0.0
        self.api_call_lock = threading.Lock()
        
        if not use_mock and GEMINI_API_KEY:
             # The media_resolution parameter is currently only available in the v1alpha API version.
             self.client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
        elif not use_mock:
             logger.warning("Initializing analyzer without Gemini API Key. Falling back to mock.")
             self.use_mock = True

    def _load_cache(self) -> Dict[str, Any]:
        """Loads analysis cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache from {self.cache_file}: {e}")
        return {}

    def _save_cache(self):
        """Saves current cache to file thread-safely."""
        with self.cache_lock:
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.analysis_cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save cache to {self.cache_file}: {e}")

    def _respect_rate_limit(self):
        """No longer artificially limiting in pay-as-you-go mode."""
        pass

    def _call_api_with_retry(self, models_to_try: List[str], contents: Any, config: types.GenerateContentConfig, max_retries: int = 3) -> Any:
        """Generic API caller with model fallback and exponential backoff."""
        retry_delay = 2 
        last_error = None
        for attempt in range(max_retries):
            for model_id in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=model_id,
                        contents=contents,
                        config=config
                    )
                    return response
                except Exception as e:
                    last_error = e
                    if "404" in str(e) or "not found" in str(e).lower():
                        logger.warning(f"Model {model_id} failed (404/Not Found). Falling back to next model.")
                        continue 
                    if "429" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Rate limit hit for {model_id}. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        break
                    if ("500" in str(e) or "503" in str(e)) and attempt < max_retries - 1:
                        logger.warning(f"Server error for {model_id}. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        break
                    logger.warning(f"API Error with {model_id}: {e}. Trying fallback if available...")
                    continue
        raise Exception(f"Max retries exceeded or all models failed. Last error: {last_error}")

    def analyze_videos_concurrently(self, videos: List[Dict[str, Any]], max_workers: int = 3) -> List[Dict[str, Any]]:
        """Analyzes a batch of videos concurrently using threads."""
        logger.info(f"Starting concurrent analysis for {len(videos)} videos (max_workers={max_workers})...")
        results = [None] * len(videos)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self.analyze_single_video, video): i 
                for i, video in enumerate(videos)
            }
            
            for future in as_completed(future_to_index):
                i = future_to_index[future]
                try:
                    results[i] = future.result()
                except Exception as e:
                    logger.error(f"Error processing video index {i}: {e}")
                    # Return original video with no analysis fallback
                    results[i] = videos[i]
                    
        return results

    def analyze_single_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes a single video ad to extract key dimensions."""
        logger.info(f"Analyzing video: {video_data.get('app_name')} - Rank {video_data.get('rank')}")
        
        video_url = video_data.get('video_url')
        with self.cache_lock:
            if video_url and video_url in self.analysis_cache:
                logger.info(f"Using cached analysis for this video URL.")
                result = video_data.copy()
                result["analysis"] = self.analysis_cache[video_url]
                return result
        
        if self.use_mock:
            result = self._mock_single_analysis(video_data)
        else:
            try:
                result = self._real_single_analysis(video_data)
            except Exception as e:
                logger.error(f"Error during video analysis for {video_data.get('app_name')}: {e}")
                logger.info("Falling back to mock data for this video.")
                result = self._mock_single_analysis(video_data)
                
        if video_url and "analysis" in result:
             with self.cache_lock:
                 self.analysis_cache[video_url] = result["analysis"]
             self._save_cache()
             
        return result

    def _real_single_analysis(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        video_url = video_data.get('video_url')
        if not video_url:
            raise ValueError("No video URL provided.")
            
        gemini_file = None
        temp_file_path = None
        
        try:
            # 1. Download video temporarily
            logger.info(f"Downloading video from {video_url[:50]}...")
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(video_url, stream=True, timeout=30, verify=False)
            response.raise_for_status()
            
            fd, temp_file_path = tempfile.mkstemp(suffix=".mp4")
            with os.fdopen(fd, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # 2. Upload to Gemini File API
            logger.info("Uploading video to Gemini...")
            gemini_file = self.client.files.upload(file=temp_file_path)
            
            # 3. Wait for processing (with timeout protection)
            logger.info("Waiting for video processing...")
            max_wait_time = 180 # 3 minutes max wait
            wait_interval = 5
            waited = 0
            
            while gemini_file.state.name == "PROCESSING":
                if waited >= max_wait_time:
                    raise TimeoutError("Video processing timed out in Gemini.")
                time.sleep(wait_interval)
                waited += wait_interval
                gemini_file = self.client.files.get(name=gemini_file.name)
                
            if gemini_file.state.name == "FAILED":
                raise Exception("Video processing failed inside Gemini.")
                
            # 4. Generate Content (Using generic caller and schema parsing)
            logger.info("Generating structural analysis...")
            prompt = f"""
            你是一位资深的移动游戏广告（特别是 SLG 策略游戏）分析专家。请分析以下视频广告。
            游戏名称: {video_data.get('app_name')}
            投放渠道: {video_data.get('ad_network')}
            
            请严格按照以下 5 个维度分析该视频的内容，并以纯 JSON 格式输出（内容必须全部是简体中文）。
            【极其重要：每个维度的分析结果极其精简，绝不能超过 50 个中文字！】
            
            1. hook_design (前 3 秒钩子设计：它是如何抓人眼球的？限50字内)
            2. emotional_appeal (情绪导向：它唤起了什么情绪？如焦虑、解压、挫败感等。限50字内)
            3. content_structure (核心内容结构：剧情的起承转合或游戏玩法的展示顺序是什么？限50字内)
            4. wow_factor (爆点/爽点要素：视频中最核心的视觉奇观或最令人满足的瞬间是什么？限50字内)
            5. copywriting_features (文案特征与 CTA：分析屏幕文字、配音台词以及转化按钮的特点。限50字内)
            """
            
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoAnalysisResult
                # Temperature is intentionally left at default (1.0) for Gemini 3 reasoning models
            )
            
            # Explicitly set media_resolution_low for video parsing to save tokens per the Gemini 3 guide
            video_part = types.Part(
                file_data=types.FileData(
                    mime_type="video/mp4",
                    file_uri=gemini_file.uri
                ),
                media_resolution={"level": "media_resolution_low"}
            )
            api_response = self._call_api_with_retry(
                models_to_try=["gemini-3-flash-preview", "gemini-2.5-flash"],
                contents=[video_part, prompt],
                config=config
            )
            
            # Use SDK's parsed object directly, fall back to json.loads if unexpectedly missing
            if getattr(api_response, 'parsed', None):
                analysis_json = api_response.parsed.model_dump()
            else:
                analysis_json = json.loads(api_response.text)
            
            result = video_data.copy()
            result["analysis"] = analysis_json
            return result
            
        finally:
            # Cleanup resources
            if gemini_file:
                try:
                    self.client.files.delete(name=gemini_file.name)
                except Exception as e:
                    logger.warning(f"Failed to delete Gemini file {gemini_file.name}: {e}")
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete local temp file {temp_file_path}: {e}")


    def generate_strategy_summary(self, applovin_analyses: List[Dict[str, Any]], facebook_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarizes both Applovin and Facebook video analyses into a strategic report."""
        logger.info("Generating strategic summary from video analyses...")
        
        if self.use_mock or (not applovin_analyses and not facebook_analyses):
            return self._mock_strategy_summary()
            
        try:
             compiled_applovin = []
             for item in applovin_analyses:
                 if "analysis" in item:
                     a = item['analysis']
                     compact = f"钩子:{a.get('hook_design','')} 情绪:{a.get('emotional_appeal','')} 结构:{a.get('content_structure','')} 爽点:{a.get('wow_factor','')} 文案:{a.get('copywriting_features','')}"
                     compiled_applovin.append(f"【Applovin Rank {item.get('rank')}】游戏:{item.get('app_name')}\n分析:{compact}")
             
             compiled_facebook = []
             for item in facebook_analyses:
                 if "analysis" in item:
                     a = item['analysis']
                     compact = f"钩子:{a.get('hook_design','')} 情绪:{a.get('emotional_appeal','')} 结构:{a.get('content_structure','')} 爽点:{a.get('wow_factor','')} 文案:{a.get('copywriting_features','')}"
                     compiled_facebook.append(f"【Facebook Rank {item.get('rank')}】游戏:{item.get('app_name')}\n分析:{compact}")
             
             analyses_text = "【Applovin 渠道 Top 素材】\n" + "\n\n".join(compiled_applovin) + "\n\n" + "【Facebook 渠道 Top 素材】\n" + "\n\n".join(compiled_facebook)
             
             prompt = f"""
             你是一位顶尖的移动游戏（特别是 SLG 品类）买量投放战略总监。
             以下是我为你提供的本周美国市场 Top 表现的爆款视频广告结构化分析结果，分为 Applovin 和 Facebook 两个主要买量渠道。
             
             【素材分析数据】
             {analyses_text}
             
             【你的任务】
             请仔细阅读这些单个视频的分析结果，然后站在宏观“大盘战略”的高度，为下周的周会提供一份精炼、深刻的总结报告。
             在总结时，请特别注意：排名越靠前的视频素材，越代表当前该渠道的主流，并且注意两个渠道之间是否存在差异化打法。
             
             请严格按照以下 3 个维度提取核心洞察，并以纯 JSON 格式输出（内容必须全部是简体中文）：
             
             1. hit_patterns (爆款投放规律：提取这些成功素材的共性机制，比如都用了什么套路、核心爽点是什么)
             2. competitor_tactics (竞品核心打法：头部竞品在买量策略和素材方向上有何转向或创新？Applovin 和 Facebook 打法是否有区分？)
             3. actionable_advice (可落地建议：针对我们自己的美术和投放团队，下周我们应该往什么方向测试创意？请给出具体的、立即可执行的建议)
             """
             
             config = types.GenerateContentConfig(
                 response_mime_type="application/json",
                 response_schema=StrategySummaryResult
                 # Temperature is intentionally left at default (1.0) for Gemini 3 reasoning models
             )
             
             api_response = self._call_api_with_retry(
                 models_to_try=["gemini-3.1-pro-preview", "gemini-2.5-pro"],
                 contents=prompt,
                 config=config
             )
             
             if getattr(api_response, 'parsed', None):
                 summary_json = api_response.parsed.model_dump()
             else:
                 summary_json = json.loads(api_response.text)
                 
             return {"strategy_summary": summary_json}
             
        except Exception as e:
            logger.error(f"Error generating strategy summary: {e}")
            return self._mock_strategy_summary()

    def _mock_single_analysis(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Returns mock structured analysis for a video."""
        result = video_data.copy()
        result.update({
            "analysis": {
                "hook_design": "展示了由于选择了错误道具导致的小游戏失败，从而引发用户的挫败感和‘一定要选对’的冲动。",
                "emotional_appeal": "轻微的焦虑感，并承诺在成功而且升级后提供巨大的满足感和解压感。",
                "content_structure": "提出危机（被僵尸包围/挨冻） -> 玩家手忙脚乱操作失败 -> 重新升级基地应对方案 -> 利用大招获得成功清屏。",
                "wow_factor": "密集且恐怖的丧尸群被范围武器瞬间秒杀，呈现极强的视觉冲击和解压感。",
                "copywriting_features": "‘只有 1% 的人能通关！’ / ‘立即下载拯救他们！’ / 紧迫的数字倒计时。"
            }
        })
        time.sleep(1) # simulate brief delay
        return result
        
    def _mock_strategy_summary(self) -> Dict[str, Any]:
         return {
            "strategy_summary": {
                "hit_patterns": "多数爆款素材高度依赖‘失败心理暗示’。素材中刻意展示并不反映真实核心玩法的低难度挫败场景，极其有效地构建了‘我上我也行’的心理预期，从而吸引点击。",
                "competitor_tactics": "头部竞品正在将超休闲玩法的解谜元素与硬核的 4X 策略背景结合，大幅降低了用户的认知门槛与核心受众的获客成本(CPA)。",
                "actionable_advice": "建议下周测试创意重心从‘城建升级’转移到‘A与B二选一’的高压互动场景，要求必须在视频前5秒内直接解决即时危机。"
            }
         }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    analyzer = VideoAnalyzer(use_mock=True)
    # Test single
    mock_vid = {"app_name": "Test Game", "rank": 1, "video_url": "dummy"}
    print("Single Analysis:\n", json.dumps(analyzer.analyze_single_video(mock_vid), indent=2))
    # Test summary
    print("\nStrategy Summary:\n", json.dumps(analyzer.generate_strategy_summary([], []), indent=2))
