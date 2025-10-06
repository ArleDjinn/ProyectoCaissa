# SMTP troubleshooting

Este repositorio incluye un pequeño script que permite diagnosticar problemas de conexión con el servidor SMTP configurado mediante variables de entorno compatibles con Flask-Mail.

## Uso

En el servidor (o localmente, si tienes las mismas variables definidas), ejecuta:

```bash
source venv/bin/activate
python scripts/test_mail_connection.py
```

El script mostrará:

- Host y puerto que está intentando usar.
- Si la conexión se hace con SSL implícito o STARTTLS.
- Si se proporcionó usuario y contraseña.
- Resultado de la autenticación y de un comando `NOOP` para comprobar la conexión.

Para activar trazas detalladas del protocolo SMTP, agrega la opción `--debug`:

```bash
python scripts/test_mail_connection.py --debug
```

Si necesitas forzar valores distintos (por ejemplo, otro puerto), puedes exportar variables antes de ejecutar el script:

```bash
export MAIL_PORT=587
export MAIL_USE_TLS=true
python scripts/test_mail_connection.py
```

## Interpretación de resultados

- `Connection error`: indica que no se pudo establecer la conexión (DNS, red o firewall).
- `login: authentication failed`: usuario/contraseña inválidos o falta de permiso (por ejemplo, si no se habilitó "Acceso a aplicaciones poco seguras" o la cuenta requiere OAuth).
- `login: success` seguido de `NOOP command: success`: la cuenta quedó autenticada correctamente.
- Usa `CTRL+C` para detener el script si queda en espera; esto puede ocurrir si hay un bloqueo de red.

Una vez diagnosticado el problema, recuerda reiniciar Gunicorn para que tome las variables de entorno actualizadas:

```bash
sudo systemctl restart caissa
```
