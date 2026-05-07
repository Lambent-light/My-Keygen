import re
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class TempInboxService:
    """
    TempInbox.xyz 临时邮箱服务
    极其小众，免费公开 API，无需任何 Key
    域名池: tempinbox.xyz, thepiratebay.cloud, cryptoblad.nl
    """

    BASE_URL = "https://endpoint.tempinbox.xyz"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

    def _get_domains(self) -> list:
        """获取可用域名列表"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/domains",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                domains = resp.json()
                if isinstance(domains, list) and domains:
                    return domains
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] TempInbox 获取域名列表失败: {e}")
        return ["tempinbox.xyz", "thepiratebay.cloud", "cryptoblad.nl"]

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建随机临时邮箱
        返回 (email, email)  -- token 直接用 email 本身作为标识
        """
        try:
            resp = requests.get(
                f"{self.BASE_URL}/email/Random",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp.status_code == 200:
                email = resp.text.strip().strip('"')
                if email and "@" in email:
                    return email, email
                else:
                    print(f"[{cfg.ts()}] [ERROR] TempInbox 返回格式异常: {resp.text}")
            else:
                print(f"[{cfg.ts()}] [ERROR] TempInbox 创建邮箱失败 (HTTP {resp.status_code}): {resp.text}")

        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] TempInbox 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, email: str) -> list:
        """
        获取指定邮箱的所有邮件
        返回邮件列表
        """
        try:
            resp = requests.get(
                f"{self.BASE_URL}/messages/{email}",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("messages", data.get("data", []))
            return []

        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] TempInbox 获取邮件异常: {e}")
            return []

    def get_message_detail(self, msg_id: str) -> dict:
        """获取单封邮件详情"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/message/{msg_id}",
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
