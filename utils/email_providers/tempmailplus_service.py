import re
import json
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class TempMailPlusService:
    """
    TempMail.Plus 临时邮箱服务
    无需 Token，完全无代码配置。
    域名比较多，支持 mailbox 控制。
    """

    API_BASE = "https://tempmail.plus/api/mails"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        # TempMail.plus 官方目前常用域名
        self.domains = ["fexbox.org", "fexbox.ru", "mailbox.in.ua", "roepyi.com", "10mail.org", "mailto.plus"]

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        生成随机邮箱名
        TempMail.plus 无需显式创建，直接生成地址去 GET 即可
        """
        try:
            domain = random.choice(self.domains)
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{mailbox}@{domain}"
            return email, email
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] TempMail.plus 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, email: str) -> list:
        """获取邮件列表"""
        try:
            params = {
                "email": email,
                "limit": 20,
                "ephemeral": 1
            }
            resp = requests.get(
                self.API_BASE,
                params=params,
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110"
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("mail_list", [])
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] TempMail.plus 获取邮件异常: {e}")
        return []

    def get_message_detail(self, email: str, msg_id: str) -> dict:
        """获取邮件单封详情"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/{msg_id}",
                params={"email": email, "ephemeral": 1},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110"
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
