# app/services/webpay.py
from datetime import datetime, timezone
from flask import current_app, url_for
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.options import WebpayOptions, IntegrationType
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_api_keys import IntegrationApiKeys


def _build_transaction() -> Transaction:
    """
    Construye la instancia de Transaction según el ambiente (integration o production).
    Usa las variables definidas en config.py (cargadas desde .env).
    """
    env = (current_app.config.get("TBK_ENV") or "integration").lower()

    if env == "integration":
        # Ambiente de integración (usa credenciales oficiales del SDK)
        opts = WebpayOptions(
            IntegrationCommerceCodes.WEBPAY_PLUS,
            IntegrationApiKeys.WEBPAY,
            IntegrationType.TEST
        )
    else:
        # Ambiente de producción (requiere credenciales reales)
        opts = WebpayOptions(
            current_app.config["TBK_COMMERCE_CODE"],
            current_app.config["TBK_API_KEY"],
            IntegrationType.PRODUCTION
        )

    return Transaction(opts)


def create_for_order(order):
    """
    Crea la transacción Webpay para una orden.
    Retorna (token, url) que se usan para redirigir al usuario a Webpay.
    """
    tx = _build_transaction()

    buy_order = f"CAISSA-{order.id}-{int(datetime.now(timezone.utc).timestamp())}"
    session_id = f"g{order.subscription.guardian_id}-o{order.id}"
    return_url = url_for("orders.webpay_return", _external=True)

    resp = tx.create(buy_order, session_id, order.amount_clp, return_url)
    token = resp["token"]
    url = resp["url"]

    return token, url


def commit_token(token: str):
    """
    Confirma la transacción en Webpay usando el token (token_ws).
    Devuelve el dict de respuesta de Transbank (con status, amount, etc).
    """
    tx = _build_transaction()
    return tx.commit(token)