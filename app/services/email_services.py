import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import Config
 
 
def enviar_correo_recuperacion(destinatario: str, nombre_completo: str, codigo: str):
    """
    Envía el código de recuperación por correo. Lanza excepción si falla el envío,
    para que la ruta que lo llama pueda informar el error sin exponer detalles sensibles.
    """
    asunto = "Código de recuperación de contraseña - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#2c3e50;">Recuperación de contraseña</h2>
        <p>Hola {nombre_completo},</p>
        <p>Recibimos una solicitud para restablecer tu contraseña en el Sistema SG-SST.
           Usa el siguiente código para continuar:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px;
                   background:#f4f6f8; padding: 12px 20px; text-align:center; border-radius:8px;">
            {codigo}
        </p>
        <p>Este código es válido por {Config.CODIGO_RECUPERACION_MINUTOS} minutos.
           Si tú no solicitaste este cambio, ignora este correo.</p>
    </div>
    """
 
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
 
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())

def enviar_correo_rechazo(destinatario: str, nombre_admin_sede: str, codigo_item: str,
                           descripcion_item: str, motivo: str):
    """Notifica al administrador de la sede que uno de sus registros fue rechazado."""
    asunto = f"Registro rechazado - Ítem {codigo_item} - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#e74c3c;">Registro rechazado</h2>
        <p>Hola {nombre_admin_sede},</p>
        <p>El administrador general revisó un registro de tu sede y lo rechazó por tener fallas.</p>
        <p><b>Ítem:</b> {codigo_item} — {descripcion_item}</p>
        <p><b>Motivo del rechazo:</b></p>
        <p style="background:#f4f6f8; padding: 12px 16px; border-left: 4px solid #e74c3c; border-radius:6px;">
            {motivo}
        </p>
        <p>Por favor corrige el registro y vuelve a enviarlo para autenticación.</p>
    </div>
    """

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())

def enviar_correo_cuenta_aprobada(destinatario: str, nombre_completo: str):
    asunto = "Tu cuenta fue aprobada - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#27ae60;">Cuenta aprobada</h2>
        <p>Hola {nombre_completo},</p>
        <p>El administrador general aprobó tu solicitud de cuenta en el Sistema SG-SST.
           Ya puedes iniciar sesión con tu usuario y contraseña.</p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())


def enviar_correo_cuenta_rechazada(destinatario: str, nombre_completo: str, motivo: str):
    asunto = "Tu solicitud de cuenta fue rechazada - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#e74c3c;">Solicitud rechazada</h2>
        <p>Hola {nombre_completo},</p>
        <p>Tu solicitud de cuenta en el Sistema SG-SST fue rechazada por el administrador general.</p>
        <p><b>Motivo:</b></p>
        <p style="background:#f4f6f8; padding: 12px 16px; border-left: 4px solid #e74c3c; border-radius:6px;">
            {motivo}
        </p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())

def enviar_correo_credenciales(destinatario: str, nombre_completo: str, usuario: str,
                                password_generada: str, nombre_rol: str, nombre_sede: str):
    asunto = "Tu cuenta fue creada - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#2c3e50;">Bienvenido al Sistema SG-SST</h2>
        <p>Hola {nombre_completo},</p>
        <p>El administrador general creó tu cuenta. Estos son tus datos de acceso:</p>
        <table style="width:100%; background:#f4f6f8; border-radius:8px; padding:12px; border-collapse:collapse;">
            <tr><td style="padding:6px 12px;"><b>Usuario:</b></td><td style="padding:6px 12px;">{usuario}</td></tr>
            <tr><td style="padding:6px 12px;"><b>Contraseña temporal:</b></td><td style="padding:6px 12px; font-family:monospace; font-size:16px;">{password_generada}</td></tr>
            <tr><td style="padding:6px 12px;"><b>Rol:</b></td><td style="padding:6px 12px;">{nombre_rol}</td></tr>
            <tr><td style="padding:6px 12px;"><b>Sede:</b></td><td style="padding:6px 12px;">{nombre_sede or "N/A"}</td></tr>
        </table>
        <p style="margin-top:1rem;">Por seguridad, te recomendamos cambiar esta contraseña después de tu primer inicio de sesión (usa la opción "¿Olvidaste tu contraseña?" en el login).</p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())
    
def enviar_correo_cambios_usuario(destinatario: str, nombre_completo: str, cambios: list):
    """'cambios' es una lista de strings, ej: ['Rol: Líder SG-SST → Administrador de sede']"""
    asunto = "Se actualizaron los datos de tu cuenta - Sistema SG-SST"
    filas_cambios = "".join(
        f'<li style="margin-bottom:6px;">{c}</li>' for c in cambios
    )
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#2c3e50;">Tu cuenta fue modificada</h2>
        <p>Hola {nombre_completo},</p>
        <p>El administrador general actualizó los siguientes datos de tu cuenta en el Sistema SG-SST:</p>
        <ul style="background:#f4f6f8; padding:16px 16px 16px 32px; border-radius:8px;">
            {filas_cambios}
        </ul>
        <p>Si no esperabas este cambio, comunícate con el administrador general.</p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())

def enviar_correo_cuenta_eliminada(destinatario: str, nombre_completo: str):
    asunto = "Tu cuenta fue eliminada - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#e74c3c;">Cuenta eliminada</h2>
        <p>Hola {nombre_completo},</p>
        <p>El administrador general eliminó tu cuenta en el Sistema SG-SST. Ya no podrás iniciar sesión ni acceder a la plataforma.</p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())

def enviar_correo_cuenta_reubicada(destinatario: str, nombre_completo: str, nombre_sede_origen: str, nombre_sede_destino: str):
    asunto = "Tu cuenta fue reubicada a otra sede - Sistema SG-SST"
    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2 style="color:#2c3e50;">Cuenta reubicada</h2>
        <p>Hola {nombre_completo},</p>
        <p>El administrador general reubicó tu cuenta del Sistema SG-SST de la sede <b>{nombre_sede_origen}</b> a la sede <b>{nombre_sede_destino}</b>.</p>
        <p>Ya puedes iniciar sesión y acceder a la nueva sede.</p>
    </div>
    """
    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{Config.SMTP_REMITENTE_NOMBRE} <{Config.SMTP_USER}>"
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        servidor.sendmail(Config.SMTP_USER, destinatario, mensaje.as_string())