import random
import string
import time
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class MoaktService:
    """
    Moakt.com 临时邮箱服务
    纯 REST JSON API，Session 会话制，零配置。
    域名极其冷门 (tmpbox.net, disbox.net 等)。
    邮箱有效期 1 小时。
    """

    BASE_URL = "https://www.moakt.com"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        # 缓存已重建的 session，避免反复创建导致 TLS 握手失败
        self._session_cache: Dict[str, requests.Session] = {}

    def _get_session(self, cookies_str: str) -> requests.Session:
        """获取或创建一个带有指定 cookies 的 Session（复用已有连接）"""
        if cookies_str in self._session_cache:
            return self._session_cache[cookies_str]

        sess = requests.Session(impersonate="chrome120")
        for cookie in cookies_str.split("; "):
            if "=" in cookie:
                k, v = cookie.split("=", 1)
                sess.cookies.set(k.strip(), v.strip())
        self._session_cache[cookies_str] = sess
        return sess

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱：
        1. GET 首页初始化 Session
        2. POST /en/inbox 创建邮箱
        返回 (email, session_cookie_string)
        """
        try:
            session = requests.Session(impersonate="chrome120")

            # 初始化 Session
            session.get(
                f"{self.BASE_URL}/en",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
            )

            # 创建邮箱
            resp = session.post(
                f"{self.BASE_URL}/en/inbox",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                addr = data.get("data", {}).get("address", {})
                email = addr.get("email", "")
                if email:
                    # 将 session cookies 序列化为 token
                    cookies_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
                    # 预存到缓存中，后续轮询直接复用这个 session
                    self._session_cache[cookies_str] = session
                    return email, cookies_str

            print(f"[{cfg.ts()}] [ERROR] Moakt 创建邮箱失败: {resp.status_code}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Moakt 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, cookies_str: str) -> list:
        """获取邮件列表（复用 Session 避免 TLS 握手反复失败）"""
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
                    data = resp.json()
                    emails = data.get("data", {}).get("emails", None)
                    return emails if isinstance(emails, list) else []
            except Exception as e:
                err_str = str(e).lower()
                # TLS 握手失败时，销毁缓存，下次重建
                if "tls" in err_str or "ssl" in err_str or "35" in err_str:
                    self._session_cache.pop(cookies_str, None)
                    if attempt == 0:
                        time.sleep(0.5)
                        continue  # 重试一次
                # 超时类错误静默处理
                if "timeout" not in err_str:
                    pass  # 轮询阶段不打印错误，避免刷屏
        return []

    def get_message_detail(self, cookies_str: str, msg_id: str) -> dict:
        """获取单封邮件详情"""
        try:
            sess = self._get_session(cookies_str)
            resp = sess.get(
                f"{self.BASE_URL}/en/inbox/{msg_id}",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
