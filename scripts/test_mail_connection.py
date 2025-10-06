"""Utility to test SMTP connectivity using Flask-Mail environment variables."""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from typing import Optional


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "t", "yes", "y"}:
        return True
    if value in {"0", "false", "f", "no", "n"}:
        return False
    return default


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mail_defaults() -> dict[str, object]:
    provider = os.environ.get("MAIL_PROVIDER", "default").strip().lower()
    if provider in {"google_workspace", "gmail"}:
        return {
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 587,
            "MAIL_USE_TLS": True,
            "MAIL_USE_SSL": False,
        }
    return {
        "MAIL_SERVER": "localhost",
        "MAIL_PORT": 25,
        "MAIL_USE_TLS": False,
        "MAIL_USE_SSL": False,
    }


def main(argv: list[str]) -> int:
    debug = "--debug" in argv

    defaults = _mail_defaults()

    server = os.environ.get("MAIL_SERVER", defaults["MAIL_SERVER"])
    port = _env_int("MAIL_PORT", int(defaults["MAIL_PORT"]))
    use_tls = _env_bool("MAIL_USE_TLS", bool(defaults["MAIL_USE_TLS"]))
    use_ssl = _env_bool("MAIL_USE_SSL", bool(defaults["MAIL_USE_SSL"]))
    timeout = float(os.environ.get("MAIL_SEND_TIMEOUT", "15"))
    username = os.environ.get("MAIL_USERNAME")
    password_present = bool(os.environ.get("MAIL_PASSWORD"))

    print("SMTP diagnostics")
    print(f"  server: {server}:{port}")
    print(f"  use_ssl: {use_ssl}")
    print(f"  use_tls: {use_tls}")
    print(f"  timeout: {timeout}s")
    print(f"  username provided: {bool(username)}")
    print(f"  password provided: {password_present}")

    smtp: Optional[smtplib.SMTP] = None

    try:
        if use_ssl:
            context = ssl.create_default_context()
            smtp = smtplib.SMTP_SSL(server, port, timeout=timeout, context=context)
        else:
            smtp = smtplib.SMTP(server, port, timeout=timeout)

        if debug and smtp is not None:
            smtp.set_debuglevel(1)

        smtp.ehlo()

        if use_tls and not use_ssl:
            context = ssl.create_default_context()
            smtp.starttls(context=context)
            smtp.ehlo()

        if username:
            try:
                smtp.login(username, os.environ.get("MAIL_PASSWORD", ""))
                print("  login: success")
            except smtplib.SMTPHeloError as exc:
                print(f"  login: failed during HELO/EHLO: {exc}")
            except smtplib.SMTPAuthenticationError as exc:
                print(f"  login: authentication failed: {exc.smtp_error.decode(errors='ignore') if isinstance(exc.smtp_error, bytes) else exc.smtp_error}")
            except smtplib.SMTPException as exc:
                print(f"  login: other SMTP error: {exc}")
            except Exception as exc:  # pragma: no cover - unexpected errors
                print(f"  login: unexpected error: {exc}")
            else:
                try:
                    smtp.noop()
                    print("  NOOP command: success")
                except smtplib.SMTPException as exc:
                    print(f"  NOOP command: error: {exc}")
        else:
            try:
                smtp.noop()
                print("  NOOP command: success")
            except smtplib.SMTPException as exc:
                print(f"  NOOP command: error: {exc}")

        return 0
    except (OSError, smtplib.SMTPException) as exc:
        print(f"Connection error: {exc}")
        return 1
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                smtp.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
