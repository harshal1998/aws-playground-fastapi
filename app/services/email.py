import logging
import smtplib
import socket
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_mock_email(item_name: str, item_price: float):
    """Sends a mock email notification to Mailpit."""
    try:
        msg = EmailMessage()
        msg.set_content(
            f"Hello!\n\nA new product '{item_name}' was registered at price ${item_price}.\n\nProcessed by container: {socket.gethostname()}"
        )
        msg["Subject"] = f"📦 New Product Added: {item_name}"
        msg["From"] = "system@fastapi-docker.local"
        msg["To"] = "admin@example.com"

        with smtplib.SMTP(settings.MAILPIT_HOST, settings.MAILPIT_PORT, timeout=3) as server:
            server.send_message(msg)
        logger.info("Sent mock email notification for %s to Mailpit", item_name)
    except (smtplib.SMTPException, OSError) as e:
        logger.warning("Mailpit notification delivery skipped: %s", e)
