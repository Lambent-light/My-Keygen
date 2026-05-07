import json
import random
import re
import string
from html import unescape
from typing import Any, Dict, List, Optional

from curl_cffi import requests

from utils import config as cfg


class EmailGeneratorOrgService:
    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.base_url = "https://www.emailgenerator.org"
        self.page_url = f"{self.base_url}/en"
        self.messages_url = f"{self.base_url}/messages"
        self.change_url = f"{self.base_url}/en/change"
        self.create_url = f"{self.base_url}/create"
        self.timeout = 30
        self.impersonations = ("chrome136", "chrome133a", "safari17_0", "safari15_3")
        self.headers = {
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.ajax_headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.page_url,
            "Origin": self.base_url,
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _new_session(self, impersonate: str):
        session = requests.Session(impersonate=impersonate)
        if self.proxies:
            session.proxies = self.proxies
        return session

    @staticmethod
    def _extract_csrf(html: str) -> str:
        if not html:
            return ""
        match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']*)', html, re.I)
        return unescape(match.group(1)).strip() if match else ""

    @staticmethod
    def _parse_cookie_string(cookie_str: str) -> Dict[str, str]:
        cookies: Dict[str, str] = {}
        for part in str(cookie_str or "").split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                cookies[key] = value
        return cookies

    def _seed_cookies(self) -> Dict[str, str]:
        cookies = self._parse_cookie_string(getattr(cfg, "EMAILGENERATOR_ORG_COOKIE", ""))
        # 避免历史 email 会话把邮箱粘回旧后缀
        cookies.pop("email", None)

        cf_clearance = str(getattr(cfg, "EMAILGENERATOR_ORG_CF_CLEARANCE", "") or "").strip()
        if cf_clearance:
            cookies["cf_clearance"] = cf_clearance
        return cookies

    def _serialize_cookies(self, session) -> List[Dict[str, str]]:
        cookies = []
        for cookie in session.cookies.jar:
            if cookie.domain and "emailgenerator.org" not in cookie.domain:
                continue
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or "www.emailgenerator.org",
                    "path": cookie.path or "/",
                }
            )
        return cookies

    def _encode_state(self, *, csrf: str, cookies: List[Dict[str, str]], mailbox: str, impersonate: str) -> str:
        return json.dumps(
            {
                "csrf": csrf,
                "cookies": cookies,
                "mailbox": mailbox,
                "impersonate": impersonate,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _decode_state(self, token: str) -> Dict[str, Any]:
        try:
            state = json.loads(token or "{}")
        except Exception:
            return {}
        return state if isinstance(state, dict) else {}

    def _session_from_state(self, state: Dict[str, Any]):
        impersonate = str(state.get("impersonate") or self.impersonations[0])
        try:
            session = self._new_session(impersonate)
        except Exception:
            session = self._new_session(self.impersonations[0])

        for cookie in state.get("cookies") or []:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            if not name:
                continue
            domain = str(cookie.get("domain") or "www.emailgenerator.org")
            path = str(cookie.get("path") or "/")
            session.cookies.set(name, value, domain=domain, path=path)
        return session

    def _post_messages(self, session, csrf: str) -> Dict[str, Any]:
        resp = session.post(
            self.messages_url,
            headers=self.ajax_headers,
            data={"_token": csrf, "captcha": ""},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 收件箱请求失败 (HTTP {resp.status_code})")
            return {}
        try:
            data = resp.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _sanitize_custom_name(name: str) -> str:
        value = str(name or "").strip().lower()
        value = re.sub(r"[^a-z0-9._-]", "", value)
        return value[:64]

    @staticmethod
    def _generate_random_name(length: int = 10) -> str:
        prefix = "eg"
        body_len = max(4, int(length) - len(prefix))
        return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=body_len))

    def _apply_seed_cookies(self, session) -> None:
        for name, value in self._seed_cookies().items():
            try:
                session.cookies.set(name, value, domain="www.emailgenerator.org", path="/")
            except Exception:
                pass

    def _create_custom_mailbox(self, session, custom_name: str, custom_domain: str) -> bool:
        try:
            resp = session.get(self.change_url, headers=self.headers, timeout=self.timeout)
            csrf = self._extract_csrf(resp.text or "")
            if resp.status_code != 200 or not csrf:
                return False

            create_resp = session.post(
                self.create_url,
                headers={
                    **self.headers,
                    "Referer": self.change_url,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"_token": csrf, "name": custom_name, "domain": custom_domain},
                allow_redirects=True,
                timeout=self.timeout,
            )
            return create_resp.status_code in {200, 302}
        except Exception:
            return False

    def create_email(self) -> tuple[Optional[str], Optional[str]]:
        configured_name = self._sanitize_custom_name(getattr(cfg, "EMAILGENERATOR_ORG_CUSTOM_NAME", ""))
        custom_domain = str(getattr(cfg, "EMAILGENERATOR_ORG_CUSTOM_DOMAIN", "") or "").strip()
        custom_name = configured_name or self._generate_random_name()
        last_error = None

        for impersonate in self.impersonations:
            try:
                session = self._new_session(impersonate)
                self._apply_seed_cookies(session)

                if custom_domain:
                    self._create_custom_mailbox(session, custom_name, custom_domain)

                resp = session.get(self.page_url, headers=self.headers, timeout=self.timeout)
                csrf = self._extract_csrf(resp.text or "")
                if resp.status_code != 200 or not csrf:
                    continue

                data = self._post_messages(session, csrf)
                mailbox = str(data.get("mailbox") or "").strip()
                if mailbox and "@" in mailbox:
                    token = self._encode_state(
                        csrf=csrf,
                        cookies=self._serialize_cookies(session),
                        mailbox=mailbox,
                        impersonate=impersonate,
                    )
                    return mailbox, token
            except Exception as e:
                last_error = e
                continue

        print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 创建邮箱失败{f': {last_error}' if last_error else ''}")
        return None, None

    def get_messages(self, token: str) -> List[Dict[str, Any]]:
        state = self._decode_state(token)
        csrf = str(state.get("csrf") or "").strip()
        if not csrf:
            return []

        try:
            session = self._session_from_state(state)
            data = self._post_messages(session, csrf)
            messages = data.get("messages", [])
            return messages if isinstance(messages, list) else []
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 获取邮件列表异常: {e}")
            return []

    def get_message_detail(self, token: str, message_id: str) -> str:
        if not message_id:
            return ""

        state = self._decode_state(token)
        try:
            session = self._session_from_state(state)
            resp = session.get(
                f"{self.base_url}/en/view/{message_id}",
                headers={"Referer": self.page_url, "Accept-Language": "en-US,en;q=0.9"},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.text or ""
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 获取邮件详情异常: {e}")
        return ""

    @staticmethod
    def _clean_html(content: str) -> str:
        text = re.sub(r"<(script|style)\b[\s\S]*?</\1>", " ", content or "", flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", unescape(text)).strip()

    def extract_code(self, content: str) -> str:
        text = self._clean_html(content)
        if not text:
            return ""

        patterns = [
            r"Your\s+(?:ChatGPT|OpenAI)\s+code\s+is\s*(\d{6})",
            r"(\d{6})\s+is\s+your\s+(?:ChatGPT|OpenAI)\s+code",
            r"(?:ChatGPT|OpenAI)\s+code\s+is\s*(\d{6})",
            r"verification\s+code\s+to\s+continue:\s*(\d{6})",
            r"enter\s+this\s+code:\s*(\d{6})",
            r"\bcode\s+is\s*(\d{6})\b",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.I)
            if matches:
                return matches[-1]

        lowered = text.lower()
        if "openai" in lowered or "chatgpt" in lowered:
            matches = re.findall(r"(?<!\d)(\d{6})(?!\d)", text)
            if matches:
                return matches[-1]
        return ""

    def get_code(self, token: str, processed_mail_ids=None) -> str:
        processed_mail_ids = processed_mail_ids if processed_mail_ids is not None else set()
        for message in self.get_messages(token):
            message_id = str(
                message.get("id")
                or message.get("_id")
                or message.get("mail_id")
                or message.get("message_id")
                or ""
            ).strip()
            if message_id and message_id in processed_mail_ids:
                continue

            compact = json.dumps(message, ensure_ascii=False)
            lowered = compact.lower()
            if "openai" not in lowered and "chatgpt" not in lowered:
                continue

            code = self.extract_code(compact)
            if not code and message_id:
                code = self.extract_code(self.get_message_detail(token, message_id))

            if code:
                if message_id:
                    processed_mail_ids.add(message_id)
                return code
        return ""
