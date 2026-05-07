import re
import json
import random
import string
from typing import Optional, Dict, List, Tuple
from curl_cffi import requests
from utils import config as cfg


class MaildropService:
    """
    Maildrop.cc 临时邮箱服务
    GraphQL API，零配置，无需认证
    公共收件箱: 任意名称@maildrop.cc 自动创建
    """

    API_URL = "https://api.maildrop.cc/graphql"
    DOMAIN = "maildrop.cc"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _graphql(self, query: str, variables: dict = None) -> dict:
        """执行 GraphQL 请求"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = requests.post(
                self.API_URL,
                json=payload,
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[{cfg.ts()}] [ERROR] Maildrop GraphQL 请求失败 (HTTP {resp.status_code})")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Maildrop GraphQL 请求异常: {e}")
        return {}

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        生成随机邮箱名
        Maildrop 不需要显式创建，只需随机一个用户名即可
        返回 (email, mailbox_name)
        """
        try:
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
            email = f"{mailbox}@{self.DOMAIN}"
            return email, mailbox
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Maildrop 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, mailbox: str) -> list:
        """获取收件箱邮件列表"""
        query = """
        query GetInbox($mailbox: String!) {
            inbox(mailbox: $mailbox) {
                id
                headerfrom
                subject
                date
            }
        }
        """
        result = self._graphql(query, {"mailbox": mailbox})
        return (result.get("data") or {}).get("inbox", [])

    def get_message_detail(self, mailbox: str, msg_id: str) -> dict:
        """获取单封邮件详情"""
        query = """
        query GetMessage($mailbox: String!, $id: ID!) {
            message(mailbox: $mailbox, id: $id) {
                id
                headerfrom
                subject
                date
                data
                html
            }
        }
        """
        result = self._graphql(query, {"mailbox": mailbox, "id": msg_id})
        return (result.get("data") or {}).get("message", {})
