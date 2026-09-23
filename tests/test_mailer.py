import smtplib
from unittest.mock import MagicMock, patch

from rental_finder.config import Settings
from rental_finder.mailer import send


def test_missing_credentials_never_touches_the_network():
    settings = Settings(gmail_address=None, gmail_app_password=None)
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        ok, message = send("landlord@example.com", "Subject", "Body", settings)
    assert ok is False
    assert "not configured" in message
    mock_smtp.assert_not_called()


def test_successful_send_logs_in_and_sends_the_right_message():
    settings = Settings(gmail_address="me@gmail.com", gmail_app_password="app-password")
    mock_conn = MagicMock()
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_conn
        ok, message = send("landlord@example.com", "Rental inquiry", "Hello there", settings)

    assert ok is True
    mock_conn.login.assert_called_once_with("me@gmail.com", "app-password")
    sent_message = mock_conn.send_message.call_args[0][0]
    assert sent_message["From"] == "me@gmail.com"
    assert sent_message["To"] == "landlord@example.com"
    assert sent_message["Subject"] == "Rental inquiry"
    assert sent_message.get_content().strip() == "Hello there"


def test_smtp_failure_is_reported_not_raised():
    settings = Settings(gmail_address="me@gmail.com", gmail_app_password="wrong")
    with patch("smtplib.SMTP_SSL") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
        ok, message = send("landlord@example.com", "Subject", "Body", settings)
    assert ok is False
    assert "SMTP error" in message


def test_connection_failure_is_reported_not_raised():
    settings = Settings(gmail_address="me@gmail.com", gmail_app_password="x")
    with patch("smtplib.SMTP_SSL", side_effect=OSError("network unreachable")):
        ok, message = send("landlord@example.com", "Subject", "Body", settings)
    assert ok is False
    assert "connection error" in message
