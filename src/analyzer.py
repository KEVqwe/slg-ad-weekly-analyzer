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

class PerAppSummaryResult(BaseModel):
    hit_patterns: str
    channel_strategy: str
    counter_strategy: str

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
             self.client = genai.Client(api_key=GEMINI_API_KEY)
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
            【极其重要：每个维度的分析结果极其精简，绝不能超过 100 个中文字！】
            
            1. hook_design (前 3 秒钩子设计：它是如何抓人眼球的？限100字内)
            2. emotional_appeal (情绪导向：它唤起了什么情绪？如焦虑、解压、挫败感等。限100字内)
            3. content_structure (核心内容结构：剧情的起承转合或游戏玩法的展示顺序是什么？限100字内)
            4. wow_factor (爆点/爽点要素：视频中最核心的视觉奇观或最令人满足的瞬间是什么？限100字内)
            5. copywriting_features (文案特征与 CTA：分析屏幕文字、配音台词以及转化按钮的特点。限50字内)
            """
            
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoAnalysisResult
            )
            
            api_response = self._call_api_with_retry(
                models_to_try=["gemini-2.5-flash"],
                contents=[gemini_file, prompt],
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


    def generate_per_app_strategy_summaries(self, all_analyzed_videos: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Summarizes video analyses on a per-app basis."""
        logger.info("Generating per-app strategic summaries...")

        if self.use_mock or not all_analyzed_videos:
            return self._mock_per_app_strategy_summaries()

        # Group videos by app
        apps_data = {}
        for video in all_analyzed_videos:
            app_name = video.get('app_name')
            if not app_name:
                continue
            if app_name not in apps_data:
                apps_data[app_name] = []
            apps_data[app_name].append(video)

        app_summaries = {}
        
        # Max concurrency for pay-as-you-go
        max_workers = min(10, len(apps_data)) if apps_data else 1
        
        def process_single_app(app_name: str, videos: List[Dict[str, Any]]) -> tuple:
            logger.info(f"Generating summary for app: {app_name}")
            
            compiled_texts = []
            for item in videos:
                if "analysis" in item:
                    a = item['analysis']
                    channel = item.get('channel', 'Unknown')
                    rank = item.get('rank', 'N/A')
                    rank_change = item.get('rank_change', 'N/A')
                    share = item.get('share', 'N/A')
                    
                    compact = f"钩子:{a.get('hook_design','')} 情绪:{a.get('emotional_appeal','')} 结构:{a.get('content_structure','')} 爽点:{a.get('wow_factor','')} 文案:{a.get('copywriting_features','')}"
                    compiled_texts.append(f"【{channel.capitalize()} 排名: {rank} (较上周变化: {rank_change}, 份额: {share})】\n分析:{compact}")
            
            analyses_text = f"【{app_name} 本周爆款素材分析数据】\n" + "\n\n".join(compiled_texts)
            
            prompt = f"""
            你是一位顶尖的移动游戏（特别是 SLG 品类）竞品买量攻防战略专家。
            以下是我们通过监控捕获的本周【{app_name}】这款游戏，在各大渠道（Applovin、Facebook、YouTube）上排名前列的爆款视频广告结构化分析结果。
            
            {analyses_text}
            
            【你的任务】
            请仔细阅读该游戏本周的爆款素材数据，深挖该游戏本周买量端的**核心动向和意图**。
            在总结时，请特别注意：
            1. 它当前主推的美术风格、包装的“爽点”或“痛点”是什么。
            2. 数据中的排名变化（如 NEW 代表本周新晋爆款，或排名上升/下降）和曝光份额。请结合这些数据，深度分析从上一周到这一周，为什么某些素材会增加曝光（如：验证了新爽点、新颖度高），而另一些会减少曝光（如：受众疲劳、方向跑偏）。
            3. 关注该游戏在不同渠道（如 Applovin vs Facebook）的素材是不是有一套相同的解法，还是呈现出了显著的差异化打法。
            4. 必须明确提示用户去重点关注哪几条你认为最有潜力、值得借鉴的素材（例如新晋高排名、排名飙升的黑马）。
            
            【⚠️ 核心排版与语言要求 ⚠️】
            1. 结构化输出：必须采用“结论先行 + 要点拆解”的结构。
            2. 极简句式：拒绝长篇大论！使用“短句 + 动词”的表达形式（如：“主打生存爽感”、“弱化城建元素”）。
            3. HTML 标签格式：你的输出是 JSON，但 JSON 的值必须包含格式化的 HTML 标签，具体格式为：
               `<strong>一句话核心动向/结论</strong><ul><li>针对性要点一（短句带动作）</li><li>针对性要点二（短句带动作）</li></ul>`
            
            请严格按照以下 3 个维度提取该竞品的核心洞察，并以纯 JSON 格式输出（内容必须全部是简体中文，且遵循上述 HTML 标签格式）：
            
            1. hit_patterns (本周核心套路与曝光增减分析：提取该游戏本周爆款素材的共性机制，它主推的核心吸量包装和用户爽点是什么？结合排名变化分析素材增减曝光的深层原因。(重点参考份额高或新上的素材))
            2. channel_strategy (渠道差异化打法：该游戏在各个渠道的投放侧重点是否存在差异？比如某一渠道主打解压，另一渠道主打擦边偏好？)
            3. counter_strategy (我方应对策略及潜力素材推荐：针对该产品的吸量点我们该如何防守或借鉴？请给出具体的素材测试建议，**并务必指出哪几条具体素材（列出特征或排名）具有爆发潜力，值得我方重点关注**。)
            """
            
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PerAppSummaryResult
            )
            
            try:
                api_response = self._call_api_with_retry(
                    models_to_try=["gemini-3.1-pro-preview", "gemini-2.5-pro"],
                    contents=prompt,
                    config=config
                )
                
                if getattr(api_response, 'parsed', None):
                    summary_json = api_response.parsed.model_dump()
                else:
                    summary_json = json.loads(api_response.text)
                    
                return (app_name, summary_json)
            except Exception as e:
                logger.error(f"Error generating summary for {app_name}: {e}")
                return (app_name, self._mock_strategy_summary_data())

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_app = {
                executor.submit(process_single_app, app_name, videos): app_name 
                for app_name, videos in apps_data.items()
            }
            
            for future in as_completed(future_to_app):
                try:
                    app_name, summary = future.result()
                    app_summaries[app_name] = summary
                except Exception as e:
                    logger.error(f"Failed to generate summary via thread: {e}")

        return app_summaries

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
        
    def _mock_per_app_strategy_summaries(self) -> Dict[str, Dict[str, Any]]:
        return {
            "Test Game 1": self._mock_strategy_summary_data(),
            "Test Game 2": self._mock_strategy_summary_data()
        }

    def _mock_strategy_summary_data(self) -> Dict[str, Any]:
        return {
            "hit_patterns": "<strong>核心依赖“失败心理暗示”构建用户预期。</strong><ul><li>刻意展示低难度失败操作</li><li>激发“我上我也行”挑战欲</li><li>承诺成功后的极致解压感</li></ul>",
            "channel_strategy": "<strong>呈现“重内容、轻认知”融合趋势。</strong><ul><li>Applovin 重直给爽感，大量投送割草画面</li><li>Facebook 重副玩法包装，侧重解谜和选错惩罚</li></ul>",
            "counter_strategy": "<strong>立刻转移测试视点至“高压互动”。</strong><ul><li>放弃传统城建升级套路</li><li>前 5 秒切入“A/B 二选一”生死局</li><li>强化即时反馈与危机解决爽感</li></ul>"
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    analyzer = VideoAnalyzer(use_mock=True)
    # Test single
    mock_vid = {"app_name": "Test Game", "rank": 1, "video_url": "dummy"}
    print("Single Analysis:\n", json.dumps(analyzer.analyze_single_video(mock_vid), indent=2))
    print("\nStrategy Summary:\n", json.dumps(analyzer.generate_per_app_strategy_summaries([]), indent=2))
