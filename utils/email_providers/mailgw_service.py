import re
import json
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class MailGwService:
    """
    Mail.gw 临时邮箱服务
    与 Mail.tm 同架构 (Hydra API)，但域名池不同
    免费、无需 API Key
    """

    API_BASE = "https://api.mail.gw"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._token = ""

    def _get_domains(self) -> list:
        """获取可用域名列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/domains",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                members = data if isinstance(data, list) else data.get("hydra:member", [])
                return [d["domain"] for d in members if d.get("isActive")]
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.gw 获取域名列表失败: {e}")
        return []

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱账号
        返回 (email, bearer_token)
        """
        try:
            domains = self._get_domains()
            if not domains:
                print(f"[{cfg.ts()}] [ERROR] Mail.gw 无可用域名")
                return None, None

            domain = random.choice(domains)
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            address = f"{username}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

            # 创建账号
            resp = requests.post(
                f"{self.API_BASE}/accounts",
                json={"address": address, "password": password},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp.status_code not in [200, 201]:
                print(f"[{cfg.ts()}] [ERROR] Mail.gw 创建账号失败 (HTTP {resp.status_code}): {resp.text[:200]}")
                return None, None

            # 获取 Bearer Token
            resp2 = requests.post(
                f"{self.API_BASE}/token",
                json={"address": address, "password": password},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp2.status_code == 200:
                token_data = resp2.json()
                token = token_data.get("token", "")
                if token:
                    self._token = token
                    return address, token

            print(f"[{cfg.ts()}] [ERROR] Mail.gw 获取 Token 失败 (HTTP {resp2.status_code})")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.gw 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, token: str) -> list:
        """获取邮件列表"""
        try:
            auth_headers = {**self.headers, "Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{self.API_BASE}/messages",
                headers=auth_headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("hydra:member", [])
            elif resp.status_code == 401:
                print(f"[{cfg.ts()}] [WARNING] Mail.gw Token 已过期")
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] Mail.gw 获取邮件异常: {e}")
        return []

    def get_message_detail(self, token: str, msg_id: str) -> dict:
        """获取邮件详情"""
        try:
            auth_headers = {**self.headers, "Authorization": f"Bearer {token}"}
            resp = requests.get(
                f"{self.API_BASE}/messages/{msg_id}",
                headers=auth_headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
