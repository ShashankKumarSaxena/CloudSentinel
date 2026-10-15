"""Opt-in SMTP delivery; configuration and credentials never enter the browser."""

from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
import os
import smtplib
import ssl


class EmailDelivery:
    def __init__(self):
        self.enabled = os.environ.get("CLOUDSENTINEL_SMTP_ENABLED") == "1"
        self.host = os.environ.get("CLOUDSENTINEL_SMTP_HOST", "")
        self.port = int(os.environ.get("CLOUDSENTINEL_SMTP_PORT", "587"))
        self.sender = os.environ.get("CLOUDSENTINEL_SMTP_FROM", "")
        self.recipients = [
            value.strip()
            for value in os.environ.get("CLOUDSENTINEL_SMTP_TO", "").split(",")
            if value.strip()
        ]
        self.username = os.environ.get("CLOUDSENTINEL_SMTP_USER", "")
        self.password_file = os.environ.get("CLOUDSENTINEL_SMTP_PASSWORD_FILE", "")
        self.tls = os.environ.get("CLOUDSENTINEL_SMTP_TLS", "starttls")
        if self.enabled:
            if (
                not self.host
                or not self.recipients
                or not self.sender
                or self.tls not in ("starttls", "ssl")
            ):
                raise ValueError("SMTP delivery requires a host, sender, recipients, and TLS mode.")
            for address in [self.sender, *self.recipients]:
                if (
                    parseaddr(address)[1] != address
                    or "@" not in address
                    or any(c in address for c in "\r\n")
                ):
                    raise ValueError("SMTP addresses must be plain, valid email addresses.")

    def send(self, alert):
        if not self.enabled:
            return False
        message = EmailMessage()
        message["Subject"] = f"CloudSentinel {alert['severity'].upper()} alert"
        message["From"], message["To"] = self.sender, ", ".join(self.recipients)
        message["Message-ID"] = f"<{alert['id']}@cloudsentinel.local>"
        message.set_content(
            f"{alert['title']}\n\nSource: {alert['source']}\nAlert ID: {alert['id']}\n"
            "Open the CloudSentinel alert inbox for evidence and review.\n"
            "Activity anomalies require human review and are not proof of an attack.\n"
        )
        try:
            password = Path(self.password_file).read_text().strip() if self.password_file else ""
            if self.username and not password:
                return False
            context = ssl.create_default_context()
            transport = (
                smtplib.SMTP_SSL(self.host, self.port, timeout=10, context=context)
                if self.tls == "ssl"
                else smtplib.SMTP(self.host, self.port, timeout=10)
            )
            with transport as server:
                if self.tls == "starttls":
                    server.starttls(context=context)
                if self.username:
                    server.login(self.username, password)
                server.send_message(message)
            return True
        except (OSError, smtplib.SMTPException):
            return False
