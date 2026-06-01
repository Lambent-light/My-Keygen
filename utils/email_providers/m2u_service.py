import json
from typing import Dict, Optional, Tuple
from urllib.parse import quote

from curl_cffi import requests

from utils import config as cfg


class M2uService:
    """
    MailToYou / m2u.io temporary mailbox service.

    Public API docs: https://m2u.io/en/api-docs
    - POST /v1/mailboxes/auto creates a random mailbox without auth/cookie/Turnstile.
    - token + view_token are both required for reading messages.
    """

    API_BASE = "https://api.m2u.io"
    ORIGIN = "https://m2u.io"
    IMPERSONATE = "chrome136"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 20
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": self.ORIGIN,
            "Referer": f"{self.ORIGIN}/zh",
        }

    def _request(self, method: str, path: str, **kwargs):
        return requests.request(
            method,
            f"{self.API_BASE}{path}",
            headers=kwargs.pop("headers", self.headers),
            proxies=self.proxies,
            timeout=kwargs.pop("timeout", self.timeout),
            impersonate=self.IMPERSONATE,
            **kwargs,
        )

    def _pack_token(self, mailbox: dict) -> str:
        return json.dumps(
            {
                "token": str(mailbox.get("token") or ""),
                "view_token": str(mailbox.get("view_token") or ""),
                "local_part": str(mailbox.get("local_part") or ""),
                "domain": str(mailbox.get("domain") or ""),
                "expires_at": str(mailbox.get("expires_at") or ""),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _unpack_token(self, token_blob: str) -> Tuple[str, str]:
        text = str(token_blob or "").strip()
        if not text:
            return "", ""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return str(data.get("token") or ""), str(data.get("view_token") or data.get("view") or "")
        except Exception:
            pass
        for sep in ("|", ":", ","):
            if sep in text:
                token, view = text.split(sep, 1)
                return token.strip(), view.strip()
        return text, ""

    def get_domains(self) -> list[str]:
        try:
            resp = self._request("GET", "/v1/domains")
            if resp.status_code == 200:
                data = resp.json()
                domains = data.get("domains", []) if isinstance(data, dict) else []
                return [str(domain).strip() for domain in domains if str(domain or "").strip()]
            print(f"[{cfg.ts()}] [ERROR] M2U 获取域名失败: {resp.status_code} {resp.text[:160]}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] M2U 获取域名异常: {e}")
        return []

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            resp = self._request("POST", "/v1/mailboxes/auto", json={})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    print(f"[{cfg.ts()}] [ERROR] M2U 创建邮箱失败: {data.get('error')} {data.get('reason', '')}")
                    return None, None
                mailbox = data.get("mailbox", {}) if isinstance(data, dict) else {}
                local_part = str(mailbox.get("local_part") or "").strip()
                domain = str(mailbox.get("domain") or "").strip()
                token = str(mailbox.get("token") or "").strip()
                view_token = str(mailbox.get("view_token") or "").strip()
                if local_part and domain and token and view_token:
                    return f"{local_part}@{domain}", self._pack_token(mailbox)
            print(f"[{cfg.ts()}] [ERROR] M2U 创建邮箱失败: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] M2U 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, token_blob: str) -> list:
        token, view_token = self._unpack_token(token_blob)
        if not token or not view_token:
            return []
        try:
            path = f"/v1/mailboxes/{quote(token, safe='')}/messages"
            resp = self._request("GET", path, params={"view": view_token})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    err = str(data.get("error") or "")
                    if err not in {"access_denied"}:
                        print(f"[{cfg.ts()}] [WARNING] M2U 收件箱返回错误: {err} {data.get('reason', '')}")
                    return []
                messages = data.get("messages", []) if isinstance(data, dict) else []
                return messages if isinstance(messages, list) else []
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] M2U 获取邮件列表异常: {e}")
        return []

    def get_message_detail(self, token_blob: str, msg_id: str) -> dict:
        token, view_token = self._unpack_token(token_blob)
        msg_id = str(msg_id or "").strip()
        if not token or not view_token or not msg_id:
            return {}
        try:
            path = f"/v1/mailboxes/{quote(token, safe='')}/messages/{quote(msg_id, safe='')}"
            resp = self._request("GET", path, params={"view": view_token})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    return {}
                message = data.get("message", data) if isinstance(data, dict) else {}
                return message if isinstance(message, dict) else {}
        except Exception:
            pass
        return {}
