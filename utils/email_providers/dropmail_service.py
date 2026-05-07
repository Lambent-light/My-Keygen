import json
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class DropMailService:
    """
    DropMail.me 临时邮箱服务
    基于 GraphQL API，需要免费生成的 af_ token
    域名池: dropmail.me, 10mail.org + 旋转域名
    """

    API_BASE = "https://dropmail.me/api/graphql"

    def __init__(self, token: str = "", proxies: Optional[Dict[str, str]] = None):
        self.token = token
        self.proxies = proxies
        self.timeout = 20
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _graphql_url(self) -> str:
        return f"{self.API_BASE}/{self.token}"

    def _execute(self, query: str, variables: dict = None) -> dict:
        """执行 GraphQL 请求"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            resp = requests.post(
                self._graphql_url(),
                headers=self.headers,
                json=payload,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                print(f"[{cfg.ts()}] [ERROR] DropMail Token 无效或过期 (HTTP 403)，请前往 https://dropmail.me/api/#get-token 重新获取")
            else:
                print(f"[{cfg.ts()}] [ERROR] DropMail GraphQL 请求失败 (HTTP {resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] DropMail GraphQL 请求异常: {e}")
        return {}

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱 session
        返回 (email, session_id)
        """
        if not self.token:
            print(f"[{cfg.ts()}] [ERROR] 未配置 DropMail Token！请前往 https://dropmail.me/api/#get-token 免费获取 af_ 开头的 token")
            return None, None

        query = """
        mutation {
            introduceSession(input: {withAddress: true}) {
                id
                expiresAt
                addresses {
                    address
                }
            }
        }
        """

        result = self._execute(query)
        data = result.get("data", {}).get("introduceSession")

        if data:
            session_id = data.get("id", "")
            addresses = data.get("addresses", [])
            if addresses and session_id:
                email = addresses[0].get("address", "")
                if email:
                    return email, session_id

        errors = result.get("errors", [])
        if errors:
            print(f"[{cfg.ts()}] [ERROR] DropMail 创建邮箱失败: {errors[0].get('message', '')}")
        else:
            print(f"[{cfg.ts()}] [ERROR] DropMail 创建邮箱失败: 返回数据异常")
        return None, None

    def get_messages(self, session_id: str) -> list:
        """
        获取 session 中的所有邮件
        """
        if not session_id:
            return []

        query = """
        query ($id: ID!) {
            session(id: $id) {
                mails {
                    id
                    fromAddr
                    toAddr
                    headerSubject
                    text
                    downloadUrl
                }
            }
        }
        """

        result = self._execute(query, {"id": session_id})
        session_data = (result.get("data") or {}).get("session")

        if session_data is None:
            return []

        return session_data.get("mails", [])

    def get_domains(self) -> list:
        """获取可用域名列表"""
        query = """
        query {
            domains {
                id
                name
                availableVia
                expiresAt
            }
        }
        """
        result = self._execute(query)
        return (result.get("data") or {}).get("domains", [])
