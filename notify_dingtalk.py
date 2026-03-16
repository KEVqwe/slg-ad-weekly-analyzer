"""
钉钉自定义机器人通知脚本
用于在周报生成后自动发送钉钉群通知，提醒团队查看最新报告。

使用方式:
  python notify_dingtalk.py                          # 自动检测当前周次
  python notify_dingtalk.py --week 2026_W11          # 手动指定周次
  python notify_dingtalk.py --webhook <URL>          # 手动指定 Webhook URL
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import logging
from datetime import datetime
from urllib import request, error
from urllib.parse import quote_plus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# GitHub Pages 报告地址
REPORT_BASE_URL = "https://kevqwe.github.io/slg-ad-weekly-analyzer/"


def sign_webhook_url(webhook_url: str, secret: str) -> str:
    """对 Webhook URL 进行 HMAC-SHA256 加签"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = quote_plus(base64.b64encode(hmac_code))
    return f"{webhook_url}&timestamp={timestamp}&sign={sign}"


def send_dingtalk_notification(webhook_url: str, week_label: str, report_url: str, secret: str = None):
    """发送钉钉 Markdown 消息通知"""

    today = datetime.now().strftime("%Y年%m月%d日")

    markdown_text = (
        f"## 北美SLG周报已更新\n\n"
        f"**{week_label}** 竞品视频广告周报已自动生成完毕，请查阅！\n\n"
        f"生成日期：{today}\n\n"
        f"[>> 点击查看最新周报]({report_url})\n\n"
        f"> 报告涵盖 Applovin / Facebook / YouTube 三大渠道 Top 30 SLG 视频广告的 AI 深度拆解与竞品分析。"
    )

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"SLG周报更新 - {week_label}",
            "text": markdown_text
        }
    }

    # 如果配置了加签密钥，对 URL 进行签名
    signed_url = sign_webhook_url(webhook_url, secret) if secret else webhook_url

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        signed_url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode") == 0:
                logger.info("✅ 钉钉通知发送成功！")
            else:
                logger.error(f"❌ 钉钉返回错误: {result}")
                sys.exit(1)
    except error.URLError as e:
        logger.error(f"❌ 发送钉钉通知失败: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="发送钉钉周报通知")
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="周报周次标识，例如 2026_W11。默认自动检测当前周次。"
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="钉钉 Webhook URL。默认从环境变量 DINGTALK_WEBHOOK 读取。"
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=None,
        help="钉钉加签密钥。默认从环境变量 DINGTALK_SECRET 读取。"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=REPORT_BASE_URL,
        help=f"报告页面 URL。默认: {REPORT_BASE_URL}"
    )
    args = parser.parse_args()

    # 确定 Webhook URL
    webhook = args.webhook or os.getenv("DINGTALK_WEBHOOK")
    if not webhook:
        logger.error("❌ 未提供钉钉 Webhook URL。请通过 --webhook 参数或 DINGTALK_WEBHOOK 环境变量设置。")
        sys.exit(1)

    # 确定加签密钥
    secret = args.secret or os.getenv("DINGTALK_SECRET")

    # 确定周次
    if args.week:
        week_label = args.week
    else:
        year, week, _ = datetime.now().isocalendar()
        week_label = f"{year}_W{week:02d}"

    logger.info(f"准备发送钉钉通知: 周次={week_label}, 报告地址={args.url}")
    send_dingtalk_notification(webhook, week_label, args.url, secret=secret)


if __name__ == "__main__":
    main()
