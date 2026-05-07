import random
import string
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class MailTmService:
    """
    Mail.tm 临时邮箱服务
    与 Mail.gw 同源（mail-dev 开源后端），但域名不同。
    当前域名: deltajohnsons.com (偏冷门)
    标准 REST API + JWT 认证，私密收件箱。
    """

    API_BASE = "https://api.mail.tm"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get_domains(self) -> list:
        """获取可用域名列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/domains",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome120",
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return [d["domain"] for d in data if d.get("isActive", True)]
                elif isinstance(data, dict):
                    members = data.get("hydra:member", [])
                    return [d["domain"] for d in members if d.get("isActive", True)]
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.tm 获取域名失败: {e}")
        return []

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱:
        1. 获取域名列表
        2. POST /accounts 注册
        3. POST /token 获取 JWT
        返回 (email, jwt_token)
        """
        try:
            domains = self._get_domains()
            if not domains:
                print(f"[{cfg.ts()}] [ERROR] Mail.tm 无可用域名")
                return None, None

            domain = random.choice(domains)
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{mailbox}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

            # 注册
            resp = requests.post(
                f"{self.API_BASE}/accounts",
                json={"address": email, "password": password},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome120",
            )

            if resp.status_code not in [200, 201]:
                print(f"[{cfg.ts()}] [ERROR] Mail.tm 注册失败: {resp.status_code} {resp.text[:80]}")
                return None, None

            # 获取 Token
            resp2 = requests.post(
                f"{self.API_BASE}/token",
                json={"address": email, "password": password},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome120",
            )

            if resp2.status_code == 200:
                token = resp2.json().get("token", "")
                if token:
                    return email, token

            print(f"[{cfg.ts()}] [ERROR] Mail.tm 获取token失败: {resp2.status_code}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.tm 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, token: str) -> list:
        """获取邮件列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/messages",
                headers={**self.headers, "Authorization": f"Bearer {token}"},
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome120",
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("hydra:member", data.get("messages", []))
        except Exception:
            pass
        return []

    def get_message_detail(self, token: str, msg_id: str) -> dict:
        """获取单封邮件详情"""
        try:
            # mail.tm 的 msg_id 可能包含 /messages/ 前缀
            clean_id = msg_id.replace("/messages/", "")
            resp = requests.get(
                f"{self.API_BASE}/messages/{clean_id}",
                headers={**self.headers, "Authorization": f"Bearer {token}"},
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome120",
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
