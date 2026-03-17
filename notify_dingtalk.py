"""
钉钉自定义机器人通知脚本
用于发送周报更新、功能发布和代码推送通知。

使用方式:
  python notify_dingtalk.py --type report --week 2026_W11
  python notify_dingtalk.py --type feature --title "新功能" --message "详情内容"
  python notify_dingtalk.py --type push --title "代码推送" --message "Commit info" --link "URL"
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


def send_dingtalk_notification(webhook_url: str, payload: dict, secret: str = None):
    """发送钉钉消息通知"""
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


def format_report_payload(week_label: str, report_url: str) -> dict:
    """格式化周报通知内容"""
    today = datetime.now().strftime("%Y年%m月%d日")
    markdown_text = (
        f"## 北美SLG周报已更新\n\n"
        f"**{week_label}** 竞品视频广告周报已自动生成完毕，请查阅！\n\n"
        f"生成日期：{today}\n\n"
        f"[>> 点击查看最新周报]({report_url})\n\n"
        f"> 报告涵盖 Applovin / Facebook / YouTube 三大渠道 Top 30 SLG 视频广告的 AI 深度拆解与竞品分析。"
    )
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"SLG周报更新 - {week_label}",
            "text": markdown_text
        }
    }


def format_feature_payload(title: str, message: str) -> dict:
    """格式化新功能通知内容"""
    markdown_text = (
        f"## ✨ 新功能发布\n\n"
        f"**任务标题**: {title}\n\n"
        f"**功能描述**: {message}\n\n"
        f"> 机器人正在持续进化，感谢关注！"
    )
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"新功能发布: {title}",
            "text": markdown_text
        }
    }


def format_push_payload(title: str, message: str, link: str = None) -> dict:
    """格式化代码推送通知内容"""
    markdown_text = (
        f"## 🚀 代码推送通知\n\n"
        f"**提交信息**: {title}\n\n"
        f"**详细变更**:\n{message}\n\n"
    )
    if link:
        markdown_text += f"[查看代码变更]({link})\n\n"
    
    markdown_text += f"> 自动化流水线已触发。"

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"代码推送: {title}",
            "text": markdown_text
        }
    }


def main():
    parser = argparse.ArgumentParser(description="发送钉钉通知")
    parser.add_argument(
        "--type",
        type=str,
        choices=["report", "feature", "push"],
        default="report",
        help="通知类型: report (周报), feature (新功能), push (代码推送)"
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="周次标识 (仅用于 report 类型)"
    )
    parser.add_argument(
        "--title",
        type=str,
        default="未命名通知",
        help="通知标题 (用于 feature 和 push 类型)"
    )
    parser.add_argument(
        "--message",
        type=str,
        default="",
        help="消息内容 (用于 feature 和 push 类型)"
    )
    parser.add_argument(
        "--link",
        type=str,
        default=None,
        help="相关链接"
    )
    parser.add_argument(
        "--webhook",
        type=str,
        default=None,
        help="钉钉 Webhook URL"
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=None,
        help="钉钉加签密钥"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=REPORT_BASE_URL,
        help=f"报告汇总页面 URL"
    )
    
    args = parser.parse_args()

    # 确定 Webhook 和 Secret
    webhook = args.webhook or os.getenv("DINGTALK_WEBHOOK")
    secret = args.secret or os.getenv("DINGTALK_SECRET")
    
    if not webhook:
        logger.error("❌ 未提供钉钉 Webhook URL。")
        sys.exit(1)

    # 根据类型构造 Payload
    if args.type == "report":
        if args.week:
            week_label = args.week
        else:
            year, week, _ = datetime.now().isocalendar()
            week_label = f"{year}_W{week:02d}"
        payload = format_report_payload(week_label, args.url)
    elif args.type == "feature":
        payload = format_feature_payload(args.title, args.message)
    elif args.type == "push":
        payload = format_push_payload(args.title, args.message, args.link)
    else:
        logger.error(f"❌ 不支持的通知类型: {args.type}")
        sys.exit(1)

    logger.info(f"发送钉钉通知类型: {args.type}")
    send_dingtalk_notification(webhook, payload, secret=secret)


if __name__ == "__main__":
    main()
