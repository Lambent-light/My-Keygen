import random
import re
import string
import time
from html import unescape
from typing import Dict, Optional, Tuple

from curl_cffi import requests

from utils import config as cfg


class MoaktService:
    """
    Moakt.com temporary mailbox service.
    Uses the public endpoints behind the normal web inbox flow.
    """

    BASE_URL = "https://www.moakt.com"
    PREFERRED_DOMAINS = (
        "drmail.in",
        "teml.net",
        "tmpeml.com",
        "tmpbox.net",
        "moakt.cc",
        "disbox.net",
        "tmpmail.org",
        "tmpmail.net",
        "tmails.net",
        "disbox.org",
        "moakt.co",
        "moakt.ws",
        "tmail.ws",
        "bareed.ws",
    )
    IMPERSONATIONS = ("chrome110", "chrome116", "chrome123", "chrome136", "safari17_0")

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._session_cache: Dict[str, requests.Session] = {}

    def _new_session(self) -> requests.Session:
        last_error = None
        for impersonate in self.IMPERSONATIONS:
            try:
                return requests.Session(impersonate=impersonate)
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"no supported curl_cffi impersonate available: {last_error}")

    def _get_session(self, cookies_str: str) -> requests.Session:
        if cookies_str in self._session_cache:
            return self._session_cache[cookies_str]

        sess = self._new_session()
        for cookie in cookies_str.split("; "):
            if "=" not in cookie:
                continue
            key, value = cookie.split("=", 1)
            sess.cookies.set(key.strip(), value.strip())
        self._session_cache[cookies_str] = sess
        return sess

    def _preferred_domain(self) -> str:
        preferred = str(getattr(cfg, "MOAKT_PREFERRED_DOMAIN", "") or "").strip().lstrip("@")
        return preferred if preferred in self.PREFERRED_DOMAINS else ""

    def _cookies_to_token(self, session: requests.Session) -> str:
        return "; ".join(f"{k}={v}" for k, v in session.cookies.items())

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            session = self._new_session()
            session.get(
                f"{self.BASE_URL}/en",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
            )

            domain = self._preferred_domain()
            if domain:
                username = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
                payload = {
                    "username": username,
                    "domain": domain,
                    "setemail": "Create",
                    "preferred_domain": "",
                }
            else:
                payload = {
                    "random": "Get a Random Address",
                    "preferred_domain": "",
                }

            resp = session.post(
                f"{self.BASE_URL}/en/inbox",
                headers=self.headers,
                proxies=self.proxies,
                data=payload,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                addr = data.get("data", {}).get("address", {})
                email = addr.get("email", "")
                if email:
                    cookies_str = self._cookies_to_token(session)
                    self._session_cache[cookies_str] = session
                    return email, cookies_str

            print(f"[{cfg.ts()}] [ERROR] Moakt create email failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Moakt create email exception: {e}")
        return None, None

    def _parse_html_messages(self, html: str) -> list:
        messages = []
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html or "", flags=re.I | re.S)
        for row in rows:
            href = re.search(r'href=["\'](?:/en)?/inbox/([^"\'/?#]+)["\']', row, flags=re.I)
            if not href:
                continue
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
            text_cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
                for cell in cells
            ]
            messages.append(
                {
                    "id": href.group(1).strip(),
                    "subject": text_cells[0] if text_cells else "",
                    "from": text_cells[1] if len(text_cells) > 1 else "",
                }
            )
        return messages

    def _strip_html(self, html: str) -> str:
        text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", html or "")
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(p|div|tr|li|td|th)>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", unescape(text)).strip()

    def _extract_labeled_html_value(self, html: str, label: str) -> str:
        pattern = (
            rf"(?is)<(?:td|th|label|span|div)\b[^>]*>\s*{re.escape(label)}\s*:?\s*</(?:td|th|label|span|div)>"
            rf"\s*<(?:td|th|span|div)\b[^>]*>(.*?)</(?:td|th|span|div)>"
        )
        match = re.search(pattern, html or "")
        return self._strip_html(match.group(1)) if match else ""

    def _parse_html_detail(self, html: str) -> dict:
        subject = (
            self._extract_labeled_html_value(html, "Subject")
            or self._extract_labeled_html_value(html, "Message Title")
        )
        sender = (
            self._extract_labeled_html_value(html, "From")
            or self._extract_labeled_html_value(html, "Sender")
        )
        body_match = re.search(
            r'(?is)<(?:div|td|section)\b[^>]*(?:id|class)=["\'][^"\']*(?:message|body|content)[^"\']*["\'][^>]*>(.*?)</(?:div|td|section)>',
            html or "",
        )
        body = self._strip_html(body_match.group(1)) if body_match else self._strip_html(html)
        return {"from": sender, "subject": subject, "text": body, "html": html, "body": body}

    def _message_id_from_item(self, item: dict, fallback: str = "") -> str:
        for key in ("id", "uuid", "mail_id", "message_id", "email_id", "key"):
            value = item.get(key)
            if value:
                return str(value).strip()
        for key in ("url", "href", "link"):
            value = str(item.get(key) or "")
            match = re.search(r"(?:/en)?/(?:inbox|email)/([^/?#\"']+)", value)
            if match:
                return match.group(1).strip()
        return str(fallback or "").strip()

    def _normalize_message_item(self, value, fallback_id: str = "") -> Optional[dict]:
        if not isinstance(value, dict):
            return None
        item = dict(value)
        msg_id = self._message_id_from_item(item, fallback_id)
        if not msg_id:
            return None
        item["id"] = msg_id
        return item

    def get_messages(self, cookies_str: str) -> list:
        for attempt in range(2):
            try:
                sess = self._get_session(cookies_str)
                resp = sess.get(
                    f"{self.BASE_URL}/en/inbox",
                    headers=self.headers,
                    proxies=self.proxies,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        return self._parse_html_messages(resp.text)
                    emails = (
                        (data.get("data", {}) if isinstance(data, dict) else {}).get("emails", None)
                        if isinstance(data, dict)
                        else None
                    )
                    if emails is None and isinstance(data, dict):
                        emails = data.get("emails", None)
                    if isinstance(emails, dict):
                        normalized = []
                        for key, value in emails.items():
                            item = self._normalize_message_item(value, key)
                            if item:
                                normalized.append(item)
                        emails = normalized
                    if isinstance(emails, list):
                        return [
                            item for item in (
                                self._normalize_message_item(value) for value in emails
                            )
                            if item
                        ]
                    return []
            except Exception as e:
                err_str = str(e).lower()
                if "tls" in err_str or "ssl" in err_str or "35" in err_str:
                    self._session_cache.pop(cookies_str, None)
                    if attempt == 0:
                        time.sleep(0.5)
                        continue
        return []

    def get_message_detail(self, cookies_str: str, msg_id: str) -> dict:
        try:
            sess = self._get_session(cookies_str)
            detail_paths = (
                f"/en/email/{msg_id}",
                f"/en/inbox/{msg_id}",
            )
            for path in detail_paths:
                resp = sess.get(
                    f"{self.BASE_URL}{path}",
                    headers=self.headers,
                    proxies=self.proxies,
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        if data.get("error") and not data.get("data"):
                            continue
                        return data
                except Exception:
                    pass
                return self._parse_html_detail(resp.text)
        except Exception:
            pass
        return {}
