"""Envío de correo.

Atenea escribe a sus aprendices en un solo caso: cuando alguien pide recuperar su
contraseña. No es una lista de novedades ni un canal de avisos, así que esto es
deliberadamente pequeño.

## Dos proveedores

`consola` no envía nada: escribe el mensaje en el registro. Es el de desarrollo, y
sirve para recorrer el flujo entero sin dar de alta un servicio ni gastar un
correo real. El enlace aparece en la terminal y se puede pegar en la app.

`smtp` envía de verdad. Necesita servidor, credenciales y un remitente verificado.

En producción, `consola` es un error de arranque: dejaría a quien olvide su
contraseña esperando un correo que nadie envió nunca, que es peor que no ofrecer
la recuperación.

## Lo que no hace

No reintenta. Si el servidor de correo no responde, la petición falla y el
aprendiz puede volver a pedirlo: es más honesto que aceptar en silencio algo que
no llegó. Un reintento con cola tendría sentido el día que haya más correos que
este.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.errors import AteneaError
from app.core.logging import get_logger

logger = get_logger("atenea.correo")


def enviar(*, destinatario: str, asunto: str, cuerpo: str) -> None:
    """Envía un correo de texto plano, o lo registra si no hay proveedor real."""
    if settings.email_provider == "consola":
        logger.info(
            "correo.simulado",
            destinatario=destinatario,
            asunto=asunto,
            cuerpo=cuerpo,
        )
        return
    _enviar_por_smtp(destinatario=destinatario, asunto=asunto, cuerpo=cuerpo)


def _enviar_por_smtp(*, destinatario: str, asunto: str, cuerpo: str) -> None:
    """Entrega el mensaje por SMTP con TLS."""
    mensaje = EmailMessage()
    mensaje["From"] = settings.email_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as servidor:
            servidor.starttls()
            if settings.smtp_user:
                servidor.login(settings.smtp_user, settings.smtp_password or "")
            servidor.send_message(mensaje)
    except Exception as error:
        # El detalle técnico se queda en el registro; al aprendiz se le dice que
        # lo intente de nuevo, que es lo único que puede hacer con esta
        # información.
        logger.warning(
            "correo.envio_fallido",
            destinatario=destinatario,
            error=type(error).__name__,
        )
        # `GENERATION_FAILED` es 502 en el catálogo (§8.6): un servicio de
        # tercero que no responde. No hay un código propio para el correo, y
        # inventar uno significaría tocar el contrato por un caso.
        raise AteneaError(
            "No pudimos enviar el correo. Inténtalo de nuevo en un momento.",
            code="GENERATION_FAILED",
        ) from error

    logger.info("correo.enviado", destinatario=destinatario, asunto=asunto)


__all__ = ["enviar"]
