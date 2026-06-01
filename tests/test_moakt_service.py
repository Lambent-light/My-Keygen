from utils.email_providers.moakt_service import MoaktService


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class DummySession:
    def __init__(self):
        self.cookies = {"tm_session": "abc123"}
        self.last_post = None
        self.next_email = "randomuser@drmail.in"

    def get(self, *args, **kwargs):
        return DummyResponse(status_code=200, payload={})

    def post(self, url, headers=None, proxies=None, data=None, timeout=None):
        self.last_post = {
            "url": url,
            "headers": headers,
            "proxies": proxies,
            "data": data,
            "timeout": timeout,
        }
        return DummyResponse(
            status_code=200,
            payload={
                "data": {
                    "address": {
                        "email": self.next_email,
                    }
                }
            },
        )


def test_create_email_uses_moakt_random_flow_by_default(monkeypatch):
    dummy = DummySession()

    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            return dummy

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)
    monkeypatch.setattr("utils.config.MOAKT_PREFERRED_DOMAIN", "")

    service = MoaktService()
    email, token = service.create_email()

    assert email == "randomuser@drmail.in"
    assert token == "tm_session=abc123"
    assert dummy.last_post is not None
    assert dummy.last_post["data"]["random"] == "Get a Random Address"
    assert dummy.last_post["data"]["preferred_domain"] == ""
    assert "domain" not in dummy.last_post["data"]
    assert "username" not in dummy.last_post["data"]


def test_create_email_posts_with_explicit_username_and_domain(monkeypatch):
    dummy = DummySession()
    dummy.next_email = "fixeduser@tmpbox.net"

    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            return dummy

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)
    monkeypatch.setattr("utils.config.MOAKT_PREFERRED_DOMAIN", "tmpbox.net")
    monkeypatch.setattr(
        "utils.email_providers.moakt_service.random.choices",
        lambda population, k: list("fixeduser1234"[:k]),
    )

    service = MoaktService()
    email, token = service.create_email()

    assert email == "fixeduser@tmpbox.net"
    assert token == "tm_session=abc123"
    assert dummy.last_post is not None
    assert dummy.last_post["data"]["domain"] == "tmpbox.net"
    assert dummy.last_post["data"]["preferred_domain"] == ""
    assert dummy.last_post["data"]["setemail"] == "Create"
    assert dummy.last_post["data"]["username"] == "fixeduser123"


def test_get_message_detail_falls_back_to_text_when_response_is_not_json(monkeypatch):
    class NonJsonResponse:
        status_code = 200
        text = "<html>Verify your email 123456</html>"

        def json(self):
            raise ValueError("not json")

    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            class _Cookies:
                def set(self, *args, **kwargs):
                    return None

            class _Sess:
                cookies = _Cookies()

                def get(self, *args, **kwargs):
                    return NonJsonResponse()

            return _Sess()

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)

    service = MoaktService()
    detail = service.get_message_detail("tm_session=abc123", "msg-1")

    assert detail["text"] == "Verify your email 123456"
    assert detail["html"] == "<html>Verify your email 123456</html>"


def test_get_message_detail_parses_html_subject_sender_and_body(monkeypatch):
    html = """
    <html>
      <table>
        <tr><td>From</td><td>noreply@tm.openai.com</td></tr>
        <tr><td>Subject</td><td>Verify your email</td></tr>
      </table>
      <div class="message-body"><p>Your OpenAI code is 123456</p></div>
    </html>
    """

    class NonJsonResponse:
        status_code = 200
        text = html

        def json(self):
            raise ValueError("not json")

    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            class _Cookies:
                def set(self, *args, **kwargs):
                    return None

            class _Sess:
                cookies = _Cookies()

                def get(self, *args, **kwargs):
                    return NonJsonResponse()

            return _Sess()

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)

    service = MoaktService()
    detail = service.get_message_detail("tm_session=abc123", "msg-1")

    assert detail["from"] == "noreply@tm.openai.com"
    assert detail["subject"] == "Verify your email"
    assert "Your OpenAI code is 123456" in detail["body"]


def test_get_message_detail_uses_email_endpoint_before_legacy_inbox_path(monkeypatch):
    requested_urls = []

    class JsonResponse:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            class _Cookies:
                def set(self, *args, **kwargs):
                    return None

            class _Sess:
                cookies = _Cookies()

                def get(self, url, *args, **kwargs):
                    requested_urls.append(url)
                    return JsonResponse(
                        {
                            "data": {
                                "email": {
                                    "from": "noreply@tm.openai.com",
                                    "subject": "Verify your email",
                                    "text": "Your OpenAI code is 555555",
                                }
                            }
                        }
                    )

            return _Sess()

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)

    service = MoaktService()
    detail = service.get_message_detail("tm_session=abc123", "msg-1")

    assert requested_urls == ["https://www.moakt.com/en/email/msg-1"]
    assert detail["data"]["email"]["text"] == "Your OpenAI code is 555555"


def test_get_messages_preserves_dict_keys_as_message_ids(monkeypatch):
    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            class _Cookies:
                def set(self, *args, **kwargs):
                    return None

            class _Sess:
                cookies = _Cookies()

                def get(self, *args, **kwargs):
                    return DummyResponse(
                        status_code=200,
                        payload={
                            "data": {
                                "emails": {
                                    "msg-123": {
                                        "from": "noreply@tm.openai.com",
                                        "subject": "Verify your email",
                                    }
                                }
                            }
                        },
                    )

            return _Sess()

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)

    service = MoaktService()
    messages = service.get_messages("tm_session=abc123")

    assert messages == [
        {
            "id": "msg-123",
            "from": "noreply@tm.openai.com",
            "subject": "Verify your email",
        }
    ]


def test_get_messages_normalizes_common_message_id_fields(monkeypatch):
    class DummyRequestsModule:
        @staticmethod
        def Session(*args, **kwargs):
            class _Cookies:
                def set(self, *args, **kwargs):
                    return None

            class _Sess:
                cookies = _Cookies()

                def get(self, *args, **kwargs):
                    return DummyResponse(
                        status_code=200,
                        payload={
                            "data": {
                                "emails": [
                                    {"mail_id": "mail-1", "subject": "Verify 1"},
                                    {"href": "/en/inbox/mail-2", "subject": "Verify 2"},
                                    {"subject": "missing id"},
                                ]
                            }
                        },
                    )

            return _Sess()

    monkeypatch.setattr("utils.email_providers.moakt_service.requests", DummyRequestsModule)

    service = MoaktService()
    messages = service.get_messages("tm_session=abc123")

    assert [message["id"] for message in messages] == ["mail-1", "mail-2"]
