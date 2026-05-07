import hashlib
import html
import json
import re
import time
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from curl_cffi import requests

from utils import config as cfg


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "\n".join(x.strip() for x in self.parts if x and x.strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class EmailMuxService:
    """
    EmailMux 临时邮箱
    - 通过站点公开前端接口创建邮箱、激活邮箱、拉取邮件列表
    - 邮件详情通过 /zh/email/<uuid> 页面中的 email-html-data 解析
    """

    BASE_URL = "https://emailmux.com"
    SECRET = "yjd683c@47"
    DOMAINS = ["gmail", "googlemail", "outlook", "hotmail", "icloud", "temp"]

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 20
        self.session = requests.Session(impersonate="chrome136")
        if proxies:
            self.session.proxies = proxies
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://emailmux.com/zh/",
            "Origin": "https://emailmux.com",
        }

    @staticmethod
    def _encode_token(email: str, baseline_ids: List[str]) -> str:
        return json.dumps(
            {
                "email": email,
                "baseline_ids": baseline_ids,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _decode_token(token: str) -> dict:
        raw = str(token or "").strip()
        if not raw:
            return {}
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"email": raw, "baseline_ids": []}

    @classmethod
    def _sign_headers(cls, email: str) -> dict:
        ts = str(int(time.time() * 1000))
        sig = hashlib.md5(f"{cls.SECRET}{email}{ts}".encode("utf-8")).hexdigest()
        return {
            "X-API-Timestamp": ts,
            "X-API-Signature": sig,
        }

    def _json_get(self, path: str, email: str) -> Tuple[dict | list | None, int]:
        headers = dict(self.headers)
        headers.update(self._sign_headers(email))
        resp = self.session.get(
            f"{self.BASE_URL}{path}",
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            return None, resp.status_code
        return resp.json(), resp.status_code

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/generate-email",
                headers=self.headers,
                json={"domains": self.DOMAINS},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                detail = ""
                try:
                    detail = str((resp.json() or {}).get("msg") or "").strip()
                except Exception:
                    detail = (resp.text or "").strip()[:200]
                if detail:
                    print(f"[{cfg.ts()}] [ERROR] EmailMux 创建邮箱失败 (HTTP {resp.status_code}): {detail}")
                else:
                    print(f"[{cfg.ts()}] [ERROR] EmailMux 创建邮箱失败 (HTTP {resp.status_code})")
                return None, None

            data = resp.json()
            status = str(data.get("status") or "").strip().lower()
            email = str(data.get("email") or "").strip()
            msg = str(data.get("msg") or "").strip()

            if status != "success" or not email:
                if msg:
                    print(f"[{cfg.ts()}] [ERROR] EmailMux 创建邮箱失败: {msg}")
                else:
                    print(f"[{cfg.ts()}] [ERROR] EmailMux 创建邮箱失败: {data}")
                return None, None

            activate_headers = dict(self.headers)
            activate_headers.update(self._sign_headers(email))
            activate = self.session.get(
                f"{self.BASE_URL}/use-email?email={quote(email, safe='')}",
                headers=activate_headers,
                timeout=self.timeout,
            )
            if activate.status_code != 200:
                print(f"[{cfg.ts()}] [ERROR] EmailMux 激活邮箱失败 (HTTP {activate.status_code})")
                return None, None

            act_data = activate.json()
            if str(act_data.get("status") or "").strip().lower() != "success":
                print(f"[{cfg.ts()}] [ERROR] EmailMux 激活邮箱失败: {act_data.get('msg') or act_data}")
                return None, None

            baseline_ids = []
            messages = self.get_messages(self._encode_token(email, []))
            for msg_item in messages:
                msg_id = str(msg_item.get("uuid") or msg_item.get("_id") or "").strip()
                if msg_id:
                    baseline_ids.append(msg_id)

            return email, self._encode_token(email, baseline_ids)
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] EmailMux 创建邮箱异常: {e}")
            return None, None

    def get_messages(self, token: str) -> list:
        meta = self._decode_token(token)
        email = str(meta.get("email") or "").strip()
        if not email:
            return []

        baseline_ids = {
            str(x).strip()
            for x in (meta.get("baseline_ids") or [])
            if str(x).strip()
        }

        try:
            data, status_code = self._json_get(
                f"/emails?email={quote(email, safe='')}",
                email,
            )
            if status_code != 200 or not isinstance(data, list):
                return []

            result = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                msg_id = str(item.get("uuid") or item.get("_id") or "").strip()
                if not msg_id or msg_id in baseline_ids:
                    continue
                result.append(
                    {
                        "uuid": msg_id,
                        "email_address": str(item.get("email_address") or "").strip(),
                        "sender": str(item.get("sender") or "").strip(),
                        "subject": str(item.get("subject") or "").strip(),
                        "timestamp": str(item.get("timestamp") or "").strip(),
                    }
                )
            return result
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] EmailMux 获取邮件异常: {e}")
            return []

    def get_message_detail(self, uuid: str) -> dict:
        if not uuid:
            return {}

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/zh/email/{quote(uuid, safe='')}",
                headers={
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": "https://emailmux.com/zh/",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return {}

            page = resp.text
            subject_match = re.search(
                r'<h2[^>]*>\s*<span[^>]*>(.*?)</span>\s*</h2>',
                page,
                re.I | re.S,
            )
            from_match = re.search(r'From:\s*([^<]+)</span>', page, re.I)
            html_match = re.search(
                r'<script id="email-html-data" type="application/json">\s*(.*?)\s*</script>',
                page,
                re.I | re.S,
            )

            html_content = ""
            if html_match:
                try:
                    html_content = json.loads(html_match.group(1))
                except Exception:
                    try:
                        html_content = html.unescape(html_match.group(1).strip().strip('"'))
                    except Exception:
                        html_content = ""

            parser = _HTMLTextExtractor()
            try:
                parser.feed(html_content)
                text_content = parser.get_text()
            except Exception:
                text_content = re.sub(r"<[^>]+>", " ", html_content or "")
                text_content = re.sub(r"\s+", " ", text_content).strip()

            return {
                "uuid": uuid,
                "subject": html.unescape(subject_match.group(1).strip()) if subject_match else "",
                "sender": html.unescape(from_match.group(1).strip()) if from_match else "",
                "html_content": html_content,
                "text_content": text_content,
            }
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] EmailMux 获取邮件详情异常: {e}")
            return {}
