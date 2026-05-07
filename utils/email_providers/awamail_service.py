import json
from typing import Dict, List, Optional, Tuple

from curl_cffi import requests

from utils import config as cfg


class AwamailService:
    """Awamail 纯 requests 版本。依赖用户预先提供 cf_clearance Cookie。"""

    BASE_URL = "https://awamail.com/welcome"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 20
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://awamail.com/?lang=zh",
            "X-Requested-With": "XMLHttpRequest",
        }

    @staticmethod
    def _parse_cookie_string(cookie_str: str) -> dict:
        cookies = {}
        for part in str(cookie_str or "").split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                cookies[key] = value
        return cookies

    def _base_cookies(self) -> dict:
        cookies = self._parse_cookie_string(getattr(cfg, 'AWAMAIL_COOKIE', ''))
        cf_clearance = str(getattr(cfg, 'AWAMAIL_CF_CLEARANCE', '') or '').strip()
        if cf_clearance and 'cf_clearance' not in cookies:
            cookies['cf_clearance'] = cf_clearance
        return cookies

    @staticmethod
    def _merge_response_cookies(cookies: dict, resp) -> dict:
        merged = dict(cookies or {})
        try:
            for key, value in resp.cookies.items():
                key = str(key).strip()
                value = str(value).strip()
                if key and value:
                    merged[key] = value
        except Exception:
            pass
        return merged

    def _bootstrap_session(self, cookies: dict) -> dict:
        warmup_headers = dict(self.headers)
        warmup_headers.pop("X-Requested-With", None)
        try:
            resp = requests.get(
                "https://awamail.com/?lang=zh",
                headers=warmup_headers,
                cookies=cookies,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate='chrome136',
            )
            if resp.status_code == 200:
                return self._merge_response_cookies(cookies, resp)
        except Exception as e:
            print(f"[{cfg.ts()}] [WARNING] Awamail 预热会话失败，将继续尝试直接创建邮箱: {e}")
        return cookies

    @staticmethod
    def _encode_token(cookies: dict) -> str:
        return json.dumps(cookies, ensure_ascii=False)

    @staticmethod
    def _decode_token(token: str) -> dict:
        raw = str(token or '').strip()
        if not raw:
            return {}
        if raw.startswith('{'):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if v}
            except Exception:
                pass
        cookies = {}
        for part in raw.split(';'):
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip()
            if key:
                cookies[key] = value
        return cookies

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        cookies = self._base_cookies()
        if 'cf_clearance' not in cookies:
            print(f"[{cfg.ts()}] [ERROR] Awamail 缺少 cf_clearance Cookie，请先在前端填写 awamail.cf_clearance 或 awamail.cookie")
            return None, None
        if 'awamail_session' not in cookies:
            cookies = self._bootstrap_session(cookies)

        try:
            resp = requests.post(
                f"{self.BASE_URL}/change_mailbox",
                headers=self.headers,
                cookies=cookies,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate='chrome136',
            )
            if resp.status_code != 200:
                print(f"[{cfg.ts()}] [ERROR] Awamail 创建邮箱失败 (HTTP {resp.status_code}): {resp.text[:200]}")
                return None, None

            data = resp.json()
            payload = data.get('data') or {}
            email = str(payload.get('email_address') or '').strip()
            cookies = self._merge_response_cookies(cookies, resp)
            session_cookie = cookies.get('awamail_session') or payload.get('awamail_session')
            if not email or not session_cookie:
                print(f"[{cfg.ts()}] [ERROR] Awamail 返回数据异常: {resp.text[:200]}")
                return None, None

            token_cookies = dict(cookies)
            token_cookies['awamail_session'] = str(session_cookie).strip()
            return email, self._encode_token(token_cookies)
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Awamail 创建邮箱异常: {e}")
            return None, None

    def get_messages(self, token: str) -> List[dict]:
        cookies = self._decode_token(token)
        if 'cf_clearance' not in cookies or 'awamail_session' not in cookies:
            return []

        try:
            resp = requests.get(
                f"{self.BASE_URL}/get_emails",
                headers=self.headers,
                cookies=cookies,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate='chrome136',
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            emails = ((data.get('data') or {}).get('emails') or [])
            return emails if isinstance(emails, list) else []
        except Exception as e:
            if 'timeout' not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] Awamail 获取邮件异常: {e}")
            return []

    def get_message_detail(self, token: str, message_id: str) -> dict:
        cookies = self._decode_token(token)
        if 'cf_clearance' not in cookies or 'awamail_session' not in cookies or not message_id:
            return {}

        try:
            resp = requests.get(
                f"{self.BASE_URL}/get_email/{message_id}",
                headers=self.headers,
                cookies=cookies,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate='chrome136',
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            detail = data.get('data') or {}
            return detail if isinstance(detail, dict) else {}
        except Exception as e:
            if 'timeout' not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] Awamail 获取邮件详情异常: {e}")
            return {}
