import re
import json
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class GuerrillaService:
    """
    GuerrillaMail 临时邮箱服务
    使用公开 API (ajax.php)
    老牌、稳定、全公开、无需认证
    """

    API_BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        获取一个新邮箱，并返回 sid_token
        """
        try:
            params = {
                "f": "get_email_address",
                "ip": "127.0.0.1",
                "agent": "Mozilla/5.0"
            }
            resp = requests.get(
                self.API_BASE,
                params=params,
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                email = data.get("email_addr")
                sid_token = data.get("sid_token")
                if email and sid_token:
                    return email, sid_token
            print(f"[{cfg.ts()}] [ERROR] GuerrillaMail: 获取邮箱失败 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] GuerrillaMail 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, sid_token: str) -> list:
        """获取邮件列表"""
        try:
            params = {
                "f": "get_email_list",
                "ip": "127.0.0.1",
                "agent": "Mozilla/5.0",
                "offset": "0",
                "sid_token": sid_token
            }
            resp = requests.get(
                self.API_BASE,
                params=params,
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("list", [])
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] GuerrillaMail 获取邮件异常: {e}")
        return []

    def get_message_detail(self, sid_token: str, msg_id: str) -> dict:
        """获取邮件详情"""
        try:
            params = {
                "f": "fetch_email",
                "email_id": msg_id,
                "sid_token": sid_token
            }
            resp = requests.get(
                self.API_BASE,
                params=params,
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
