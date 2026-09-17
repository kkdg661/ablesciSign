import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

import ablesci


class FakeNotifier:
    instances = []

    def __init__(self, title):
        self.title = title
        self.notify_enabled = False
        self.messages = []
        self.__class__.instances.append(self)

    def log(self, message, level="info"):
        self.messages.append((message, level))


class FakeAutomator:
    outcomes = iter(())

    def __init__(self, email, password, notifier):
        self.email = email
        self.password = password
        self.notifier = notifier

    def run(self):
        return next(self.__class__.outcomes)


class AccountParsingTests(unittest.TestCase):
    def test_credentials_are_not_written_to_stdout(self):
        secret = "user@example.com:very-secret-password"
        output = io.StringIO()

        with patch.dict(os.environ, {ablesci.ENV_ACCOUNTS: secret}, clear=False):
            with contextlib.redirect_stdout(output):
                accounts = ablesci.get_accounts()

        self.assertEqual(accounts, [("user@example.com", "very-secret-password")])
        self.assertNotIn("user@example.com", output.getvalue())
        self.assertNotIn("very-secret-password", output.getvalue())

    def test_common_account_formats_are_supported(self):
        secret = (
            "colon@example.com:colon-password\n"
            "wide@example.com：wide-password\n"
            "comma@example.com,comma-password;"
            "equals@example.com=equals-password\n"
            "pipe@example.com|pipe-password\n"
            "space@example.com space-password"
        )

        with patch.dict(os.environ, {ablesci.ENV_ACCOUNTS: secret}, clear=False):
            accounts = ablesci.get_accounts()

        self.assertEqual(
            accounts,
            [
                ("colon@example.com", "colon-password"),
                ("wide@example.com", "wide-password"),
                ("comma@example.com", "comma-password"),
                ("equals@example.com", "equals-password"),
                ("pipe@example.com", "pipe-password"),
                ("space@example.com", "space-password"),
            ],
        )

    def test_password_may_contain_punctuation(self):
        secret = "user@example.com:p:a,ss=word|with;punctuation"

        with patch.dict(os.environ, {ablesci.ENV_ACCOUNTS: secret}, clear=False):
            accounts = ablesci.get_accounts()

        self.assertEqual(
            accounts,
            [("user@example.com", "p:a,ss=word|with;punctuation")],
        )


class CsrfTokenTests(unittest.TestCase):
    def setUp(self):
        self.notifier = FakeNotifier("test")
        self.automator = ablesci.AbleSciAuto(
            "user@example.com",
            "not-used",
            notifier=self.notifier,
        )

    def set_login_page(self, html, status_code=200):
        response = Mock(status_code=status_code, text=html)
        self.automator.session.get = Mock(return_value=response)

    def test_reads_token_from_new_meta_element(self):
        self.set_login_page(
            '<meta name="csrf-token" content=" new-token ">'
            '<input type="hidden" data-csrf-field value="">'
        )

        self.assertEqual(self.automator.get_csrf_token(), "new-token")

    def test_falls_back_to_legacy_hidden_input(self):
        self.set_login_page('<input type="hidden" name="_csrf" value="old-token">')

        self.assertEqual(self.automator.get_csrf_token(), "old-token")

    def test_rejects_empty_javascript_csrf_shell(self):
        self.set_login_page('<input type="hidden" data-csrf-field value="">')

        self.assertEqual(self.automator.get_csrf_token(), "")
        self.assertTrue(
            any(
                level == "error" and "页面结构可能再次变化" in message
                for message, level in self.notifier.messages
            )
        )


class MainExitStatusTests(unittest.TestCase):
    def setUp(self):
        FakeNotifier.instances.clear()

    @patch.object(ablesci, "Notifier", FakeNotifier)
    @patch.object(ablesci, "get_accounts", return_value=[])
    def test_missing_accounts_returns_failure(self, _get_accounts):
        self.assertEqual(ablesci.main(), 1)

    @patch.object(ablesci, "AbleSciAuto", FakeAutomator)
    @patch.object(ablesci, "Notifier", FakeNotifier)
    @patch.object(
        ablesci,
        "get_accounts",
        return_value=[("one@example.com", "one"), ("two@example.com", "two")],
    )
    def test_any_failed_account_returns_failure(self, _get_accounts):
        FakeAutomator.outcomes = iter((True, False))
        self.assertEqual(ablesci.main(), 1)

    @patch.object(ablesci, "AbleSciAuto", FakeAutomator)
    @patch.object(ablesci, "Notifier", FakeNotifier)
    @patch.object(
        ablesci,
        "get_accounts",
        return_value=[("one@example.com", "one"), ("two@example.com", "two")],
    )
    def test_all_successful_accounts_return_success(self, _get_accounts):
        FakeAutomator.outcomes = iter((True, True))
        self.assertEqual(ablesci.main(), 0)


if __name__ == "__main__":
    unittest.main()
