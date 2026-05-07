import asyncio
import json
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import websockets

from utils import config as cfg


class EmailToolHubService:
    """
    EmailToolHub Inbox Checker 共享邮箱池
    - 无需注册 / 无需 API Key
    - 底层通过 Socket.IO WebSocket 拉取固定测试地址的最新邮件列表
    - 这是公开共享邮箱池，不是私有临时邮箱
    """

    WS_URL = "wss://inbox-checker.emailtoolhub.com/socket.io/?EIO=4&transport=websocket"
    ADDRESS_POOL = [
        "pepapihsyd@gmail.com",
        "thomasadward5@gmail.com",
        "stellajamsonusa@gmail.com",
        "foodazmaofficial@gmail.com",
        "watsonjetpeter@gmail.com",
        "dcruzjovita651@gmail.com",
        "doctsashawn@gmail.com",
        "syedtestm@yahoo.com",
        "vexabyteofficial@yahoo.com",
        "jordanmercus1975@yahoo.com",
        "jamie_roberts@zohomail.in",
        "rollyriders@zohomail.in",
        "pollywilmar@zohomail.in",
        "awesome.jamii@yandex.com",
        "boudreauryan@yandex.com",
        "cinthianicola@aol.com",
        "fedricknicosta@aol.com",
    ]
    SNAPSHOT_TTL_SECONDS = 6
    ERROR_COOLDOWN_SECONDS = 15
    _snapshot_cache: dict = {}
    _snapshot_ts: float = 0.0
    _fetch_lock = threading.Lock()
    _cooldown_until: float = 0.0
    _last_error_log_ts: float = 0.0
    _last_error_log_text: str = ""

    def __init__(self, proxies: Optional[Dict[str, str]] = None):
        self.proxies = proxies
        self.timeout = 12

    @staticmethod
    def _encode_token(email: str, baseline_ids: List[str], created_at: str) -> str:
        return json.dumps(
            {
                "email": email,
                "baseline_ids": baseline_ids,
                "created_at": created_at,
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
        return {"email": raw, "baseline_ids": [], "created_at": ""}

    @staticmethod
    def _parse_dt(value: str) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    @classmethod
    def _log_fetch_issue(cls, message: str):
        now = time.time()
        if message == cls._last_error_log_text and (now - cls._last_error_log_ts) < 15:
            return
        cls._last_error_log_text = message
        cls._last_error_log_ts = now
        print(f"[{cfg.ts()}] [WARNING] {message}")

    async def _fetch_all_emails_async(self) -> dict:
        async with websockets.connect(
            self.WS_URL,
            open_timeout=self.timeout,
            close_timeout=2,
            max_size=2 ** 24,
            ping_interval=None,
        ) as ws:
            first = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            if not isinstance(first, str) or not first.startswith("0"):
                raise RuntimeError("engine.io 握手失败")

            await ws.send("40")

            deadline = time.monotonic() + self.timeout
            connected = False
            while time.monotonic() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic()))
                if msg == "2":
                    await ws.send("3")
                    continue
                if isinstance(msg, str) and msg.startswith("40"):
                    connected = True
                    break
            if not connected:
                raise TimeoutError("socket.io 命名空间连接超时")

            await ws.send('42["subscribeEmails"]')
            await ws.send('42["getAllEmails"]')

            while time.monotonic() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic()))
                if msg == "2":
                    await ws.send("3")
                    continue
                if isinstance(msg, str) and msg.startswith('42["allEmailsResponse",'):
                    payload = json.loads(msg[2:])
                    if (
                        isinstance(payload, list)
                        and len(payload) >= 2
                        and isinstance(payload[1], dict)
                    ):
                        data = payload[1].get("data") or {}
                        if isinstance(data, dict):
                            return data
            raise TimeoutError("未在规定时间内收到 allEmailsResponse")

    def _run_fetch_once(self) -> Tuple[dict, str]:
        try:
            data = asyncio.run(self._fetch_all_emails_async())
            return data, ""
        except RuntimeError as e:
            if "asyncio.run()" in str(e):
                loop = asyncio.new_event_loop()
                try:
                    data = loop.run_until_complete(self._fetch_all_emails_async())
                    return data, ""
                finally:
                    loop.close()
            return {}, str(e)
        except Exception as e:
            return {}, str(e)

    def _fetch_all_emails(self, force: bool = False) -> dict:
        now = time.time()
        cache = self.__class__._snapshot_cache
        if (
            not force
            and cache
            and (now - self.__class__._snapshot_ts) <= self.SNAPSHOT_TTL_SECONDS
        ):
            return cache

        if not force and now < self.__class__._cooldown_until and cache:
            return cache

        with self.__class__._fetch_lock:
            now = time.time()
            cache = self.__class__._snapshot_cache
            if (
                not force
                and cache
                and (now - self.__class__._snapshot_ts) <= self.SNAPSHOT_TTL_SECONDS
            ):
                return cache
            if not force and now < self.__class__._cooldown_until and cache:
                return cache

            last_error = ""
            for attempt in range(2):
                data, err = self._run_fetch_once()
                if data:
                    self.__class__._snapshot_cache = data
                    self.__class__._snapshot_ts = time.time()
                    self.__class__._cooldown_until = 0.0
                    return data
                last_error = err or "未知错误"
                if attempt == 0:
                    time.sleep(0.8)

            if "503" in last_error:
                self.__class__._cooldown_until = time.time() + self.ERROR_COOLDOWN_SECONDS

            if cache:
                self._log_fetch_issue(f"EmailToolHub 实时拉取失败，已回退到最近缓存快照: {last_error}")
                return cache

            self._log_fetch_issue(f"EmailToolHub 暂时无法连接共享测试池: {last_error}")
            return {}

    def _choose_address(self, snapshot: dict) -> str:
        now = datetime.now(timezone.utc)
        scored = []
        for email in self.ADDRESS_POOL:
            messages = snapshot.get(email) or []
            recent_count = 0
            for msg in messages:
                dt = self._parse_dt(msg.get("date"))
                if dt and (now - dt) <= timedelta(minutes=30):
                    recent_count += 1
            scored.append((recent_count, len(messages), random.random(), email))

        if not scored:
            return random.choice(self.ADDRESS_POOL)

        scored.sort(key=lambda item: (item[0], item[1], item[2]))
        best_recent = scored[0][0]
        best_bucket = [item[3] for item in scored if item[0] <= best_recent + 1][:5]
        return random.choice(best_bucket or [scored[0][3]])

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            snapshot = self._fetch_all_emails()
            email = self._choose_address(snapshot)
            baseline_ids = []
            for msg in (snapshot.get(email) or []):
                msg_id = str(msg.get("_id") or msg.get("id") or "").strip()
                if msg_id:
                    baseline_ids.append(msg_id)
            token = self._encode_token(
                email=email,
                baseline_ids=baseline_ids,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            return email, token
        except Exception as e:
            print(f"[{cfg.ts()}] [ERROR] EmailToolHub 创建邮箱异常: {e}")
            return None, None

    def get_messages(self, token: str) -> list:
        meta = self._decode_token(token)
        email = str(meta.get("email") or "").strip().lower()
        if not email:
            return []

        baseline_ids = {
            str(x).strip()
            for x in (meta.get("baseline_ids") or [])
            if str(x).strip()
        }
        created_at = self._parse_dt(meta.get("created_at"))

        snapshot = self._fetch_all_emails()
        messages = snapshot.get(email) or []
        result = []

        for msg in messages:
            msg_id = str(msg.get("_id") or msg.get("id") or "").strip()
            if not msg_id or msg_id in baseline_ids:
                continue

            msg_dt = self._parse_dt(msg.get("date"))
            if created_at and msg_dt and msg_dt < (created_at - timedelta(seconds=10)):
                continue

            result.append(
                {
                    "_id": msg_id,
                    "subject": str(msg.get("subject") or "").strip(),
                    "name": str(msg.get("name") or "").strip(),
                    "from": str(msg.get("from") or "").strip(),
                    "date": str(msg.get("date") or "").strip(),
                    "folder": str(msg.get("folder") or "").strip(),
                }
            )

        return result
