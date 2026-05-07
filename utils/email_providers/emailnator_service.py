import re
import urllib.parse
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class EmailnatorService:
    """
    Emailnator 临时邮箱服务
    核心能力：生成 Gmail dot-alias / plus-alias / googlemail.com 地址
    域名是 gmail.com / googlemail.com —— 不在任何临时邮箱黑名单中！
    
    工作原理：
    - dotGmail: 利用 Gmail 忽略点号的特性 (a.b.c@gmail.com = abc@gmail.com)
    - plusGmail: 利用 Gmail plus寻址 (user+tag@gmail.com)  
    - googleMail: 使用 googlemail.com 别名
    
    API 流程：
    1. GET / -> 获取 XSRF-TOKEN + session cookie
    2. POST /generate-email -> 生成邮箱
    3. POST /message-list -> 轮询收件箱
    """

    BASE_URL = "https://www.emailnator.com"

    # 推荐使用 dotGmail，因为 plus-alias 可能被 OpenAI 过滤
    EMAIL_TYPES = ["dotGmail", "plusGmail", "googleMail"]

    def __init__(self, proxies: Optional[Dict[str, str]] = None, email_type: str = "dotGmail"):
        self.proxies = proxies
        self.timeout = 15
        self.email_type = email_type if email_type in self.EMAIL_TYPES else "dotGmail"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._session_cache: Dict[str, requests.Session] = {}

    def _init_session(self) -> Tuple[requests.Session, str]:
        """初始化 Session 并获取 XSRF token"""
        sess = requests.Session(impersonate="chrome120")
        sess.get(
            f"{self.BASE_URL}/",
            headers={**self.headers, "Accept": "text/html"},
            proxies=self.proxies,
            timeout=self.timeout,
        )
        xsrf_raw = sess.cookies.get("XSRF-TOKEN", "")
        xsrf = urllib.parse.unquote(xsrf_raw)
        return sess, xsrf

    def _api_headers(self, xsrf: str) -> dict:
        """构建 API 请求头"""
        return {
            **self.headers,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": xsrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.BASE_URL}/",
            "Origin": self.BASE_URL,
        }

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建 Gmail 别名邮箱
        返回 (email, session_token)
        session_token 是序列化的 cookies 字符串
        """
        try:
            sess, xsrf = self._init_session()

            resp = sess.post(
                f"{self.BASE_URL}/generate-email",
                json={"email": [self.email_type]},
                headers=self._api_headers(xsrf),
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                emails = data.get("email", [])
                if emails:
                    email = emails[0] if isinstance(emails, list) else str(emails)
                    # 序列化 session cookies + xsrf
                    token = json.dumps({
                        "cookies": {k: v for k, v in sess.cookies.items()},
                        "xsrf": xsrf,
                        "email": email,
                    })
                    # 缓存 session
                    self._session_cache[email] = (sess, xsrf)
                    return email, token

            print(f"[{cfg.ts()}] [ERROR] Emailnator 生成邮箱失败: {resp.status_code} {resp.text[:80]}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Emailnator 创建邮箱异常: {e}")
        return None, None

    def _restore_session(self, token: str) -> Tuple[Optional[requests.Session], str, str]:
        """从 token 恢复 session"""
        try:
            data = json.loads(token)
            email = data.get("email", "")
            
            # 检查缓存
            if email in self._session_cache:
                sess, xsrf = self._session_cache[email]
                return sess, xsrf, email

            # 重建 session
            xsrf = data.get("xsrf", "")
            cookies = data.get("cookies", {})
            sess = requests.Session(impersonate="chrome120")
            for k, v in cookies.items():
                sess.cookies.set(k, v)
            self._session_cache[email] = (sess, xsrf)
            return sess, xsrf, email
        except Exception:
            return None, "", ""

    def get_messages(self, token: str) -> list:
        """获取邮件列表"""
        sess, xsrf, email = self._restore_session(token)
        if not sess or not email:
            return []

        try:
            resp = sess.post(
                f"{self.BASE_URL}/message-list",
                json={"email": email},
                headers=self._api_headers(xsrf),
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("messageData", data.get("messages", []))
        except Exception:
            pass
        return []

    def get_message_detail(self, token: str, msg_id: str) -> str:
        """获取单封邮件详情"""
        sess, xsrf, email = self._restore_session(token)
        if not sess:
            return ""

        try:
            resp = sess.post(
                f"{self.BASE_URL}/message-list",
                json={"email": email, "messageID": msg_id},
                headers=self._api_headers(xsrf),
                proxies=self.proxies,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return ""


# 需要 json 模块
import json
