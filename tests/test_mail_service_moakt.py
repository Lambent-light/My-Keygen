import io
import sys
import types
import unittest
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


class _FakeMoaktService:
    detail_calls = 0
    nested_detail = False
    mail_id_field = False
    detail_only_headers = False

    def __init__(self, proxies=None):
        pass

    def get_messages(self, jwt):
        if type(self).detail_only_headers:
            return [{"id": "msg-1"}]
        if type(self).mail_id_field:
            return [{"mail_id": "msg-1", "from": "noreply@tm.openai.com", "subject": "Verify your email"}]
        return [{"id": "msg-1", "from": "noreply@tm.openai.com", "subject": "Verify your email"}]

    def get_message_detail(self, jwt, msg_id):
        type(self).detail_calls += 1
        if type(self).detail_only_headers:
            return {
                "data": {
                    "message": {
                        "from": "noreply@tm.openai.com",
                        "subject": "Verify your email",
                        "text": "Your OpenAI code is 444444",
                    }
                }
            }
        if type(self).nested_detail:
            return {"data": {"email": {"html": "<p>Your OpenAI code is 333333</p>"}}}
        if type(self).detail_calls == 1:
            return {"data": {"body": "Your OpenAI code is 111111"}}
        return {"data": {"body": "Your OpenAI code is 222222"}}


class MailServiceMoaktTests(unittest.TestCase):
    def test_moakt_allows_new_code_from_same_message_thread(self):
        processed = set()
        _FakeMoaktService.detail_calls = 0
        _FakeMoaktService.nested_detail = False
        _FakeMoaktService.mail_id_field = False
        _FakeMoaktService.detail_only_headers = False

        with patch.object(cfg, "EMAIL_API_MODE", "moakt"), patch.object(cfg, "USE_PROXY_FOR_EMAIL", False):
            with patch("utils.email_providers.moakt_service.MoaktService", _FakeMoaktService):
                with redirect_stdout(io.StringIO()):
                    first = get_oai_code("user@example.com", jwt="cookie-token", processed_mail_ids=processed, max_attempts=1)
                    second = get_oai_code("user@example.com", jwt="cookie-token", processed_mail_ids=processed, max_attempts=1)

        self.assertEqual("111111", first)
        self.assertEqual("222222", second)
        self.assertEqual(2, len(processed))

    def test_moakt_extracts_code_from_nested_detail_payload(self):
        processed = set()
        _FakeMoaktService.detail_calls = 0
        _FakeMoaktService.nested_detail = True
        _FakeMoaktService.mail_id_field = False
        _FakeMoaktService.detail_only_headers = False

        with patch.object(cfg, "EMAIL_API_MODE", "moakt"), patch.object(cfg, "USE_PROXY_FOR_EMAIL", False):
            with patch("utils.email_providers.moakt_service.MoaktService", _FakeMoaktService):
                with redirect_stdout(io.StringIO()):
                    code = get_oai_code("user@example.com", jwt="cookie-token", processed_mail_ids=processed, max_attempts=1)

        self.assertEqual("333333", code)

    def test_moakt_extracts_code_when_message_uses_mail_id_field(self):
        processed = set()
        _FakeMoaktService.detail_calls = 0
        _FakeMoaktService.nested_detail = False
        _FakeMoaktService.mail_id_field = True
        _FakeMoaktService.detail_only_headers = False

        with patch.object(cfg, "EMAIL_API_MODE", "moakt"), patch.object(cfg, "USE_PROXY_FOR_EMAIL", False):
            with patch("utils.email_providers.moakt_service.MoaktService", _FakeMoaktService):
                with redirect_stdout(io.StringIO()):
                    code = get_oai_code("user@example.com", jwt="cookie-token", processed_mail_ids=processed, max_attempts=1)

        self.assertEqual("111111", code)

    def test_moakt_uses_sender_subject_from_detail_when_list_is_sparse(self):
        processed = set()
        _FakeMoaktService.detail_calls = 0
        _FakeMoaktService.nested_detail = False
        _FakeMoaktService.mail_id_field = False
        _FakeMoaktService.detail_only_headers = True

        with patch.object(cfg, "EMAIL_API_MODE", "moakt"), patch.object(cfg, "USE_PROXY_FOR_EMAIL", False):
            with patch("utils.email_providers.moakt_service.MoaktService", _FakeMoaktService):
                with redirect_stdout(io.StringIO()):
                    code = get_oai_code("user@example.com", jwt="cookie-token", processed_mail_ids=processed, max_attempts=1)

        self.assertEqual("444444", code)


if __name__ == "__main__":
    unittest.main()
