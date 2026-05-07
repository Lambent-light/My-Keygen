import hashlib
import random
import string
import time
from typing import Optional, Dict, Tuple
from curl_cffi import requests
from utils import config as cfg


class MailTdService:
    """
    Mail.td 临时邮箱服务 (前身 Mail.cx)
    极其小众，域名异常冷门 (sugtbt.com, qabq.com, nqmo.com, end.tw, uuf.me, 6n9.net)
    需要实现 Hashcash-style PoW (SHA-256 前导零)
    """

    API_BASE = "https://mail.td/api"

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 15
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _check_leading_zeros(hash_bytes: bytes, difficulty: int) -> bool:
        """检查 SHA-256 哈希前导零比特数是否达到 difficulty"""
        full_bytes = difficulty // 8
        remaining_bits = difficulty % 8
        for i in range(full_bytes):
            if hash_bytes[i] != 0:
                return False
        if remaining_bits > 0 and full_bytes < len(hash_bytes):
            mask = (0xFF << (8 - remaining_bits)) & 0xFF
            if (hash_bytes[full_bytes] & mask) != 0:
                return False
        return True

    @staticmethod
    def _solve_pow(address: str, timestamp: int, difficulty: int = 15) -> str:
        """
        Hashcash-style PoW: 找到 nonce 使得 SHA256(address + timestamp + nonce) 有足够的前导零
        """
        prefix = address + str(timestamp)
        nonce = 0
        while True:
            data = prefix + str(nonce)
            h = hashlib.sha256(data.encode()).digest()
            if MailTdService._check_leading_zeros(h, difficulty):
                return str(nonce)
            nonce += 1
            if nonce > 10_000_000:  # 安全上限
                raise RuntimeError("PoW 计算超限")

    def _get_domains(self) -> list:
        """获取可用域名列表"""
        try:
            resp = requests.get(
                f"{self.API_BASE}/domains",
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                domains = data.get("domains", [])
                return [d["domain"] for d in domains if not d.get("pro_only", False)]
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.td 获取域名失败: {e}")
        return []

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建临时邮箱:
        1. 获取域名列表
        2. 生成随机密码, 计算 auth_key (SHA-256 hex)
        3. 解 PoW
        4. POST /accounts 注册
        5. POST /token 获取 JWT
        返回 (email, jwt_token)
        """
        try:
            domains = self._get_domains()
            if not domains:
                print(f"[{cfg.ts()}] [ERROR] Mail.td 无可用域名")
                return None, None

            domain = random.choice(domains)
            mailbox = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{mailbox}@{domain}"
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            auth_key = hashlib.sha256(password.encode()).hexdigest()

            # 解 PoW
            ts = int(time.time())
            difficulty = 15
            nonce = self._solve_pow(email, ts, difficulty)

            # 注册账号
            resp = requests.post(
                f"{self.API_BASE}/accounts",
                json={
                    "address": email,
                    "auth_key": auth_key,
                    "pow": {"t": ts, "n": nonce, "d": difficulty}
                },
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp.status_code not in [200, 201]:
                print(f"[{cfg.ts()}] [ERROR] Mail.td 注册失败: {resp.status_code} {resp.text[:100]}")
                return None, None

            # 注册成功的响应通常已包含 token 和 id
            create_data = resp.json()
            token = create_data.get("token", "")
            account_id = create_data.get("id", "")

            if token and account_id:
                combined = f"{token}|||{account_id}"
                return email, combined

            # 如果注册响应不包含 token，走 /token 端点
            resp2 = requests.post(
                f"{self.API_BASE}/token",
                json={"address": email, "auth_key": auth_key},
                headers=self.headers,
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )

            if resp2.status_code == 200:
                token_data = resp2.json()
                token = token_data.get("token", "")
                account_id = token_data.get("id", "")
                combined = f"{token}|||{account_id}"
                return email, combined

            print(f"[{cfg.ts()}] [ERROR] Mail.td 获取token失败: {resp2.status_code}")
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] Mail.td 创建邮箱异常: {e}")
        return None, None

    def get_messages(self, combined_token: str) -> list:
        """获取邮件列表"""
        try:
            parts = combined_token.split("|||")
            if len(parts) != 2:
                return []
            token, account_id = parts
            resp = requests.get(
                f"{self.API_BASE}/accounts/{account_id}/messages?page=1",
                headers={**self.headers, "Authorization": f"Bearer {token}"},
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("messages", data) if isinstance(data, dict) else data if isinstance(data, list) else []
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"[{cfg.ts()}] [ERROR] Mail.td 获取邮件异常: {e}")
        return []

    def get_message_detail(self, combined_token: str, msg_id: str) -> dict:
        """获取单封邮件详情"""
        try:
            parts = combined_token.split("|||")
            if len(parts) != 2:
                return {}
            token, account_id = parts
            resp = requests.get(
                f"{self.API_BASE}/accounts/{account_id}/messages/{msg_id}",
                headers={**self.headers, "Authorization": f"Bearer {token}"},
                proxies=self.proxies,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
