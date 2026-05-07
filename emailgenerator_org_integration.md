# EmailGenerator.org 临时邮箱服务接入代码

本文档把本项目中 `EmailGenerator.org` 临时邮箱服务相关代码单独整理出来，便于查看、迁移或二次修改。

启用模式值：

```yaml
email_api_mode: "emailgenerator_org"
```

依赖：

```python
from curl_cffi import requests
```

## 1. Provider 文件

项目路径：

```text
utils/email_providers/emailgenerator_org_service.py
```

完整代码：

```python
import json
import re
from html import unescape
from typing import Optional, Dict, Any, List

from curl_cffi import requests
from utils import config as cfg


class EmailGeneratorOrgService:
    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.base_url = "https://www.emailgenerator.org"
        self.page_url = f"{self.base_url}/en"
        self.messages_url = f"{self.base_url}/messages"
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

    def _extract_csrf(self, html: str) -> str:
        if not html:
            return ""
        match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']*)', html, re.I)
        return unescape(match.group(1)).strip() if match else ""

    def _serialize_cookies(self, session) -> List[Dict[str, str]]:
        cookies = []
        for cookie in session.cookies.jar:
            if cookie.domain and "emailgenerator.org" not in cookie.domain:
                continue
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain or "www.emailgenerator.org",
                "path": cookie.path or "/",
            })
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

    def create_email(self) -> tuple[Optional[str], Optional[str]]:
        for impersonate in self.impersonations:
            try:
                session = self._new_session(impersonate)
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

        print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 创建邮箱失败{f': {last_error}' if 'last_error' in locals() else ''}")
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

    def _clean_html(self, content: str) -> str:
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
```

## 2. 邮箱创建接入

项目路径：

```text
utils/email_providers/mail_service.py
```

放在 `get_email_and_token()` 的 provider 分支中：

```python
if mode == "emailgenerator_org":
    try:
        from utils.email_providers.emailgenerator_org_service import EmailGeneratorOrgService
        eg_service = EmailGeneratorOrgService(proxies=mail_proxies)
        email, token = eg_service.create_email()

        if email and token:
            set_last_email(email)
            print(f"[{cfg.ts()}] [INFO] EmailGenerator.org 成功创建邮箱: ({mask_email(email)})")
            return email, token
        else:
            print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 获取邮箱失败")
    except Exception as e:
        print(f"[{cfg.ts()}] [ERROR] EmailGenerator.org 流程异常: {e}")
    return None, None
```

## 3. 验证码轮询接入

项目路径：

```text
utils/email_providers/mail_service.py
```

放在 `get_oai_code()` 的轮询分支中：

```python
elif mode == "emailgenerator_org":
    if not jwt:
        print(f"\n[{cfg.ts()}] [ERROR] EmailGenerator.org 缺少凭证，无法提取验证码！")
        return ""
    try:
        from utils.email_providers.emailgenerator_org_service import EmailGeneratorOrgService
        eg_service = EmailGeneratorOrgService(proxies=mail_proxies)
        code = eg_service.get_code(jwt, processed_mail_ids=processed_mail_ids)
        if code:
            print(
                f"\n[{cfg.ts()}] [SUCCESS] EmailGenerator.org ({mask_email(email)})邮箱提取成功: {code}")
            return code

    except Exception as e:
        pass
```

## 4. 前端模式选项

项目路径：

```text
index.html
```

下拉选项：

```html
<option value="emailgenerator_org">EmailGenerator.org</option>
```

模式说明卡片：

```html
<div v-if="config.email_api_mode === 'emailgenerator_org'" class="space-y-4 mt-2 animate-fade-in">
    <div class="flex items-center gap-2 mb-4">
        <span class="text-xs font-black text-amber-800 bg-amber-100 px-3 py-1.5 rounded-md border border-amber-200 shadow-sm uppercase tracking-wider">当前模式</span>
        <span class="text-sm font-black text-slate-700">EmailGenerator.org</span>
    </div>
    <div class="text-xs text-emerald-800 font-bold bg-emerald-50 border border-emerald-200 p-4 rounded-xl leading-relaxed shadow-sm">
        <p class="flex items-center gap-1.5 text-sm"><span>✅</span> 已接入 EmailGenerator.org</p>
        <p class="mt-2 text-emerald-700 opacity-90">系统会创建一次性邮箱，并复用同一会话轮询收件箱验证码。</p>
        <p class="mt-3 text-rose-600 font-black bg-rose-50/50 p-2 rounded-lg border border-rose-100">提示：此站点有 Cloudflare 防护，建议开启邮箱代理并使用质量较好的节点。</p>
    </div>
</div>
```

## 5. 单测

项目路径：

```text
tests/test_emailgenerator_org_service.py
```

完整代码：

```python
import unittest

from utils.email_providers.emailgenerator_org_service import EmailGeneratorOrgService


class EmailGeneratorOrgServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = EmailGeneratorOrgService()

    def test_extracts_csrf_token_from_homepage(self):
        html = '<meta name="csrf-token" content="abc123">'

        self.assertEqual("abc123", self.service._extract_csrf(html))

    def test_state_round_trip_keeps_mailbox_and_cookies(self):
        token = self.service._encode_state(
            csrf="csrf-value",
            cookies=[{"name": "emailgenerator_session", "value": "cookie-value", "domain": "www.emailgenerator.org", "path": "/"}],
            mailbox="test@uxmil.com",
            impersonate="chrome136",
        )

        state = self.service._decode_state(token)

        self.assertEqual("csrf-value", state["csrf"])
        self.assertEqual("test@uxmil.com", state["mailbox"])
        self.assertEqual("emailgenerator_session", state["cookies"][0]["name"])

    def test_extracts_openai_code_from_html(self):
        html = "<html><body>123456 is your OpenAI code</body></html>"

        self.assertEqual("123456", self.service.extract_code(html))

    def test_get_code_checks_detail_page_when_list_has_openai_subject(self):
        self.service.get_messages = lambda token: [
            {"id": 42, "from_email": "noreply@tm.openai.com", "subject": "Verify your email"}
        ]
        self.service.get_message_detail = lambda token, message_id: "Your ChatGPT code is 654321"
        processed = set()

        code = self.service.get_code("state-token", processed_mail_ids=processed)

        self.assertEqual("654321", code)
        self.assertIn("42", processed)


if __name__ == "__main__":
    unittest.main()
```

运行单测：

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m unittest discover -s tests -p "test_emailgenerator_org_service.py"
```

## 6. 接入流程摘要

1. 访问 `https://www.emailgenerator.org/en` 获取页面和 CSRF token。
2. 使用同一 session POST `/messages`，带 `_token` 和空 `captcha`。
3. 从返回 JSON 的 `mailbox` 字段拿到临时邮箱地址。
4. 将 `csrf + cookies + mailbox + impersonate` 编码成 token，供后续轮询复用。
5. 轮询时继续 POST `/messages` 获取邮件列表。
6. 如果列表里含 OpenAI/ChatGPT 线索，先从列表 payload 提取 6 位验证码；提取不到再请求 `/en/view/{message_id}` 详情页。
