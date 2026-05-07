import re
import json
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class MailsacService:
    """
    Mailsac.com 临时邮箱服务
    公共收件箱模式: 任意 xxx@mailsac.com 自动创建
    免费公共收件箱无需 API Key（注意：公共收件箱所有人可见）
    付费模式可用私有收件箱 + API Key
    """

    API_BASE = "https://mailsac.com/api"
    DOMAIN = "mailsac.com"

    def __init__(self, api_key: str = "", proxies: Optional[Dict[str, str]] = None):
        self.api_key = api_key
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        if self.api_key:
            self.headers["Mailsac-Key"] = self.api_key

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        生成随机邮箱名
        返回 (email, email)
        """
        if not self.api_key:
            print(f"[{cfg.ts()}] [ERROR] Mailsac: [未配置 API Key] Mailsac 的邮件读取 API 必须配置官方 Key 才能使用。")
            return None, None
            
        try:
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
            email = f"{mailbox}@{self.DOMAIN}"
            return email, email
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mailsac 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, email: str) -> list:
        """获取邮件列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/addresses/{email}/messages",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return []
            elif resp.status_code == 401:
                print(f"[{cfg.ts()}] [WARNING] Mailsac: 需要 API Key 才能通过 API 访问")
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] Mailsac 获取邮件异常: {e}")
        return []

    def get_message_detail(self, email: str, msg_id: str) -> dict:
        """获取邮件详情"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/addresses/{email}/messages/{msg_id}",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    def get_message_body(self, email: str, msg_id: str) -> str:
        """获取纯文本邮件正文"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/text/{email}/{msg_id}",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return ""
