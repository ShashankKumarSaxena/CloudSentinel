import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.notifications import EmailDelivery


class NotificationTest(unittest.TestCase):
    def test_disabled_delivery_never_opens_smtp(self):
        with patch.dict(os.environ, {'CLOUDSENTINEL_SMTP_ENABLED': '0'}), patch('backend.app.notifications.smtplib.SMTP') as smtp:
            self.assertFalse(EmailDelivery().send({}))
            smtp.assert_not_called()

    def test_tls_email_has_stable_id_and_does_not_include_cloud_credentials(self):
        settings = {'CLOUDSENTINEL_SMTP_ENABLED': '1', 'CLOUDSENTINEL_SMTP_HOST': 'smtp.example.test',
                    'CLOUDSENTINEL_SMTP_FROM': 'sender@example.test', 'CLOUDSENTINEL_SMTP_TO': 'receiver@example.test',
                    'CLOUDSENTINEL_SMTP_TLS': 'starttls', 'CLOUDSENTINEL_SMTP_USER': '', 'CLOUDSENTINEL_SMTP_PASSWORD_FILE': ''}
        with patch.dict(os.environ, settings), patch('backend.app.notifications.smtplib.SMTP') as smtp:
            transport = smtp.return_value.__enter__.return_value
            alert = {'id': 'alert-id', 'severity': 'critical', 'title': 'Storage finding', 'source': 'demo'}
            self.assertTrue(EmailDelivery().send(alert))
            transport.starttls.assert_called_once()
            message = transport.send_message.call_args.args[0]
            self.assertEqual(message['Message-ID'], '<alert-id@cloudsentinel.local>')
            self.assertIn('Source: demo', message.get_content())

    def test_invalid_addresses_and_plaintext_tls_are_rejected(self):
        settings = {'CLOUDSENTINEL_SMTP_ENABLED': '1', 'CLOUDSENTINEL_SMTP_HOST': 'smtp.example.test',
                    'CLOUDSENTINEL_SMTP_FROM': 'sender@example.test', 'CLOUDSENTINEL_SMTP_TO': 'bad\naddress', 'CLOUDSENTINEL_SMTP_TLS': 'starttls'}
        with patch.dict(os.environ, settings), self.assertRaises(ValueError):
            EmailDelivery()
        settings['CLOUDSENTINEL_SMTP_TO'] = 'receiver@example.test'
        settings['CLOUDSENTINEL_SMTP_TLS'] = 'plain'
        with patch.dict(os.environ, settings), self.assertRaises(ValueError):
            EmailDelivery()
