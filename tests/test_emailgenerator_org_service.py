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
