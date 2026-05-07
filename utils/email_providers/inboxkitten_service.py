import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg

class InboxKittenService:
    """
    InboxKitten 临时邮箱服务 (基于开源方案设计)
    只支持收信，完全免注册和零配置。域名是 inboxkitten.com。
    """

    API_BASE = "https://inboxkitten.com/api/v1/mail"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        self.domain = "inboxkitten.com"

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        生成随机邮箱
        邮箱前缀允许英文字母和数字，最大推荐长度14位。
        """
        try:
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{mailbox}@{self.domain}"
            return email, mailbox
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] InboxKitten 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, mailbox: str) -> list:
        """获取邮件列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/list",
                params={"recipient": mailbox},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110"
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] InboxKitten 获取邮件异常: {e}")
        return []

    def get_message_detail(self, storage_region: str, storage_key: str) -> str:
        """
        获取 HTML/文本 邮件正文
        依据 InboxKitten API: mailKey=storage-{region}-{key}
        """
        try:
            mail_key = f"storage-{storage_region}-{storage_key}"
            resp = requests.get(
                f"{self.API_BASE}/getHtml",
                params={"mailKey": mail_key},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110"
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return ""
