import time
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class MinuteInboxService:
    """
    MinuteInbox.com 临时邮箱服务
    PHP Session 会话制，JSON API，零配置。
    域名 minafter.com 等，极小众。
    关键：第一次 GET/POST 触发分配，需等待 1-2 秒后再次 GET 才能拿到邮箱。
    """

    BASE_URL = "https://www.minuteinbox.com"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._session_cache: Dict[str, requests.Session] = {}

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱：
        1. GET 首页 -> 建立 PHP Session
        2. GET /index/index -> 触发邮箱分配（首次返回 null）
        3. 轮询最多 5 次，每次间隔递增，直到拿到邮箱
        返回 (email, PHPSESSID)
        """
        try:
            session = requests.Session(impersonate="chrome120")

            # Step 1: 建立 Session（访问首页拿 PHPSESSID）
            session.get(
                f"{self.BASE_URL}/",
                headers={**self.headers, "Accept": "text/html"},
                proxies=self.proxies,
                timeout=self.timeout,
            )

            # Step 2: 首次请求触发邮箱分配
            session.get(
                f"{self.BASE_URL}/index/index",
                headers={**self.headers, "Referer": f"{self.BASE_URL}/"},
                proxies=self.proxies,
                timeout=self.timeout,
            )

            # Step 3: 轮询获取邮箱（服务端需要时间分配，通过代理更慢）
            for attempt in range(5):
                time.sleep(2)  # 每次等 2 秒

                resp = session.get(
                    f"{self.BASE_URL}/index/index",
                    headers={**self.headers, "Referer": f"{self.BASE_URL}/"},
                    proxies=self.proxies,
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        email = data.get("email")
                        if email:
                            phpsessid = session.cookies.get("PHPSESSID", "")
                            if phpsessid:
                                self._session_cache[phpsessid] = session
                            return email, phpsessid
                    except Exception:
                        pass

            print(f"[{cfg.ts()}] [ERROR] MinuteInbox 创建邮箱失败: 5次轮询均未获取到邮箱")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] MinuteInbox 创建邮箱异常: {e}")
        return None, None

    def _get_session(self, phpsessid: str) -> requests.Session:
        """获取或创建带 PHPSESSID 的 Session"""
        if phpsessid in self._session_cache:
            return self._session_cache[phpsessid]

        sess = requests.Session(impersonate="chrome120")
        sess.cookies.set("PHPSESSID", phpsessid)
        self._session_cache[phpsessid] = sess
        return sess

    def get_messages(self, phpsessid: str) -> list:
        """获取邮件列表"""
        try:
            sess = self._get_session(phpsessid)
            resp = sess.get(
                f"{self.BASE_URL}/index/refresh",
                headers={**self.headers, "Referer": f"{self.BASE_URL}/"},
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                text = resp.text.strip()
                if not text:
                    return []

                # 尝试 JSON 解析
                try:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("emails", data.get("messages", []))
                except Exception:
                    pass

                # HTML 片段解析 - 提取邮件行
                import re
                rows = re.findall(
                    r'data-id=["\']([^"\']+)["\'].*?class=["\']from["\'][^>]*>([^<]+)<.*?class=["\']subject["\'][^>]*>([^<]+)<',
                    text, re.DOTALL
                )
                messages = []
                for msg_id, sender, subject in rows:
                    messages.append({
                        "id": msg_id.strip(),
                        "from": sender.strip(),
                        "subject": subject.strip()
                    })
                return messages

        except Exception as e:
            err_str = str(e).lower()
            if "tls" in err_str or "ssl" in err_str:
                self._session_cache.pop(phpsessid, None)
        return []

    def get_message_detail(self, phpsessid: str, msg_id: str) -> str:
        """获取单封邮件正文"""
        try:
            sess = self._get_session(phpsessid)
            resp = sess.get(
                f"{self.BASE_URL}/email/id/{msg_id}",
                headers={**self.headers, "Referer": f"{self.BASE_URL}/"},
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return ""
