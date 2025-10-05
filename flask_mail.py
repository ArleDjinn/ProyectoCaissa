from contextlib import contextmanager
from typing import Iterable, List, Optional

from flask import current_app


class Message:
    def __init__(
        self,
        subject: str = "",
        recipients: Optional[Iterable[str]] = None,
        body: str | None = None,
        html: str | None = None,
        sender: Optional[str] = None,
    ):
        self.subject = subject
        self.recipients = list(recipients or [])
        self.body = body or ""
        self.html = html
        self.sender = sender


class Mail:
    def __init__(self, app=None):
        self.app = None
        self.suppress = False
        self.default_sender: Optional[str] = None
        self._record_stack: List[List[Message]] = []
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self.suppress = bool(app.config.get("MAIL_SUPPRESS_SEND", False))
        self.default_sender = app.config.get("MAIL_DEFAULT_SENDER")
        app.extensions["mail"] = self

    def send(self, message: Message):
        if message.sender is None:
            message.sender = self.default_sender or current_app.config.get(
                "MAIL_DEFAULT_SENDER"
            )
        if self._record_stack:
            self._record_stack[-1].append(message)
        if self.suppress:
            return
        # In this minimal implementation we do not perform real SMTP delivery.

    @contextmanager
    def record_messages(self):
        store: List[Message] = []
        self._record_stack.append(store)
        try:
            yield store
        finally:
            self._record_stack.pop()