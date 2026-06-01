import io
import sys
import types
from contextlib import redirect_stdout
from unittest.mock import patch

fake_requests_module = types.SimpleNamespace(Session=object, post=None, get=None)
sys.modules.setdefault("curl_cffi", types.SimpleNamespace(requests=fake_requests_module))
sys.modules.setdefault(
    "utils.integrations.ai_service",
    types.SimpleNamespace(AIService=object),
)
sys.modules.setdefault(
    "utils.email_providers.gmail_service",
    types.SimpleNamespace(get_gmail_otp_via_oauth=lambda *args, **kwargs: ""),
)
sys.modules.setdefault(
    "utils.email_providers.duckmail_service",
    types.SimpleNamespace(DuckMailService=object),
)
sys.modules.setdefault("socks", types.SimpleNamespace(SOCKS5=1, HTTP=2, socksocket=object))

from utils import config as cfg
from utils.email_providers.mail_service import get_oai_code


class _FakeM2uService:
    detail_calls = 0

    def __init__(self, proxies=None):
        pass

    def get_messages(self, jwt):
        return [{"id": "msg-1", "from_addr": "noreply@tm.openai.com", "subject": "Verify your email"}]

    def get_message_detail(self, jwt, msg_id):
        type(self).detail_calls += 1
        return {
            "id": msg_id,
            "from_addr": "noreply@tm.openai.com",
            "subject": "Verify your email",
            "text_body": "Your OpenAI verification code is 123456",
            "html_body": "<p>Your OpenAI verification code is 123456</p>",
        }


def test_mail_service_extracts_m2u_openai_code():
    processed = set()
    _FakeM2uService.detail_calls = 0

    with patch.object(cfg, "EMAIL_API_MODE", "m2u"), patch.object(cfg, "USE_PROXY_FOR_EMAIL", False):
        with patch("utils.email_providers.m2u_service.M2uService", _FakeM2uService):
            with redirect_stdout(io.StringIO()):
                code = get_oai_code("alice@tmail.bio", jwt='{"token":"tok123","view_token":"view456"}', processed_mail_ids=processed, max_attempts=1)

    assert code == "123456"
    assert _FakeM2uService.detail_calls == 1
    assert len(processed) == 1
