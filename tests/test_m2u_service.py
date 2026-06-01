import json

from utils.email_providers.m2u_service import M2uService


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def test_create_email_packs_token_and_view_token(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        assert method == "POST"
        assert url == "https://api.m2u.io/v1/mailboxes/auto"
        assert kwargs["json"] == {}
        return DummyResponse(
            payload={
                "mailbox": {
                    "token": "tok123",
                    "view_token": "view456",
                    "local_part": "alice",
                    "domain": "tmail.bio",
                    "expires_at": "2026-05-23T00:00:00.000Z",
                }
            }
        )

    monkeypatch.setattr("utils.email_providers.m2u_service.requests.request", fake_request)

    service = M2uService()
    email, token_blob = service.create_email()

    assert email == "alice@tmail.bio"
    data = json.loads(token_blob)
    assert data["token"] == "tok123"
    assert data["view_token"] == "view456"
    assert calls


def test_get_messages_uses_dual_token_query(monkeypatch):
    requested = {}

    def fake_request(method, url, **kwargs):
        requested.update({"method": method, "url": url, "kwargs": kwargs})
        return DummyResponse(payload={"messages": [{"id": "msg-1", "from_addr": "noreply@tm.openai.com", "subject": "Verify"}]})

    monkeypatch.setattr("utils.email_providers.m2u_service.requests.request", fake_request)

    service = M2uService()
    token_blob = json.dumps({"token": "tok123", "view_token": "view456"})
    messages = service.get_messages(token_blob)

    assert messages[0]["id"] == "msg-1"
    assert requested["method"] == "GET"
    assert requested["url"] == "https://api.m2u.io/v1/mailboxes/tok123/messages"
    assert requested["kwargs"]["params"] == {"view": "view456"}


def test_get_message_detail_unwraps_message(monkeypatch):
    requested = {}

    def fake_request(method, url, **kwargs):
        requested.update({"method": method, "url": url, "kwargs": kwargs})
        return DummyResponse(
            payload={
                "message": {
                    "id": "msg-1",
                    "from_addr": "noreply@tm.openai.com",
                    "subject": "Verify your email",
                    "text_body": "Your OpenAI code is 654321",
                }
            }
        )

    monkeypatch.setattr("utils.email_providers.m2u_service.requests.request", fake_request)

    service = M2uService()
    token_blob = json.dumps({"token": "tok123", "view_token": "view456"})
    detail = service.get_message_detail(token_blob, "msg-1")

    assert detail["text_body"] == "Your OpenAI code is 654321"
    assert requested["url"] == "https://api.m2u.io/v1/mailboxes/tok123/messages/msg-1"
    assert requested["kwargs"]["params"] == {"view": "view456"}


def test_unpack_token_supports_legacy_pipe_format():
    service = M2uService()
    assert service._unpack_token("tok123|view456") == ("tok123", "view456")
