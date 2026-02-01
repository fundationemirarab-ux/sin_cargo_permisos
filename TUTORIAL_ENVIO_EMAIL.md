# Tutorial: Cómo Replicar el Sistema de Envío de Emails con la API de Gmail

Este documento explica cómo configurar un nuevo proyecto en Python para enviar correos electrónicos a través de la API de Gmail, utilizando el mismo método de autenticación y envío que en este proyecto.

---

### Paso 1: Configuración en Google Cloud Console

Antes de escribir código, necesitas configurar tu proyecto en Google y obtener las credenciales.

1.  **Crea un Proyecto**: Ve a la [Google Cloud Console](https://console.cloud.google.com/) y crea un nuevo proyecto (o selecciona uno existente).
2.  **Habilita la API de Gmail**:
    *   En el menú de navegación, ve a **APIs y servicios > Biblioteca**.
    *   Busca "Gmail API" y haz clic en **Habilitar**.
3.  **Configura la Pantalla de Consentimiento OAuth**:
    *   Ve a **APIs y servicios > Pantalla de consentimiento de OAuth**.
    *   Elige el tipo de usuario **Externo** y haz clic en **Crear**.
    *   Rellena la información obligatoria (nombre de la app, correo de usuario, correo de desarrollador). Guarda y continúa.
    *   En la sección de **Permisos**, no añadas nada por ahora. Guarda y continúa.
    *   En la sección de **Usuarios de prueba**, añade la dirección de Gmail desde la que quieres enviar los correos. Esto es crucial, de lo contrario la autenticación fallará.
4.  **Crea las Credenciales**:
    *   Ve a **APIs y servicios > Credenciales**.
    *   Haz clic en **+ CREAR CREDENCIALES** y selecciona **ID de cliente de OAuth**.
    *   En **Tipo de aplicación**, selecciona **Aplicación de escritorio**.
    *   Dale un nombre (ej. "Gmail Desktop Client") y haz clic en **Crear**.
    *   Se abrirá una ventana con tu **ID de cliente** y **Secreto del cliente**. Haz clic en **DESCARGAR JSON**.
    *   Renombra el archivo descargado a `credentials.json` y guárdalo en la raíz de tu nuevo proyecto. **¡Este archivo es secreto y no debe compartirse!**

---

### Paso 2: Preparar el Entorno del Proyecto

Ahora, configura tu entorno de desarrollo en Python.

1.  **Crea un archivo `requirements.txt`** con las siguientes librerías:

    ```
    google-api-python-client
    google-auth-oauthlib
    python-dotenv
    ```

2.  **Instala las librerías**: Abre tu terminal y ejecuta:

    ```bash
    pip install -r requirements.txt
    ```

---

### Paso 3: Generar el `refresh_token`

El `refresh_token` es una credencial de larga duración que permite a tu aplicación obtener nuevos tokens de acceso sin que tengas que autorizarla cada vez.

1.  **Crea un archivo llamado `generate_token.py`**. Este script te guiará en el proceso de autorización para obtener tu primer `refresh_token`.

    ```python
    import os
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Asegúrate de que estos SCOPES coincidan con los que necesitas.
    # Para enviar correos, solo necesitas el de gmail.send.
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.send'
    ]

    def main():
        """
        Ejecuta el flujo de autenticación para obtener y mostrar un refresh_token.
        """
        if not os.path.exists('credentials.json'):
            print("Error: No se encuentra el archivo 'credentials.json'.")
            print("Por favor, descárgalo desde Google Cloud Console y ponlo en esta carpeta.")
            return
            
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        
        # Esto abrirá una ventana en tu navegador para que inicies sesión
        # y autorices la aplicación.
        creds = flow.run_local_server(port=0)

        # Imprime el refresh_token para que lo copies.
        print("\n--- ¡Copia el siguiente REFRESH_TOKEN! ---\\n")
        print(creds.refresh_token)
        print("\n--- ¡Copia el token de arriba y pégalo en tu archivo .env! ---\\n")

    if __name__ == '__main__':
        main()
    ```

2.  **Ejecuta el script**: Asegúrate de que `credentials.json` esté en la misma carpeta y ejecuta:

    ```bash
    python generate_token.py
    ```
    Se abrirá tu navegador. Inicia sesión con la cuenta de Google que configuraste como **usuario de prueba**. Autoriza los permisos que la aplicación solicita. Al terminar, la terminal te mostrará el `refresh_token`. Cópialo para el siguiente paso.

---

### Paso 4: Configurar las Variables de Entorno

Las credenciales secretas no deben estar escritas directamente en el código. Usa un archivo `.env` para gestionarlas.

1.  **Crea un archivo `.env`** en la raíz de tu proyecto.
2.  **Añade las siguientes variables**:

    ```bash
    # Extraído de tu archivo credentials.json
    GMAIL_CLIENT_ID="TU_ID_DE_CLIENTE"
    GMAIL_CLIENT_SECRET="TU_SECRETO_DE_CLIENTE"

    # Obtenido del script generate_token.py
    GMAIL_REFRESH_TOKEN="EL_TOKEN_QUE_ACABAS_DE_GENERAR"

    # El email desde el que se enviarán los correos
    SENDER_EMAIL="tu_email@gmail.com"
    ```
    *   Copia y pega los valores de `client_id` y `client_secret` desde tu archivo `credentials.json`.
    *   Pega el `refresh_token` que obtuviste en el paso anterior.
    *   Añade el email que vas a usar para enviar los correos.

---

### Paso 5: Implementar el Código para Enviar Correos

Finalmente, aquí está el código de Python para usar estas credenciales y enviar un correo.

Puedes crear un archivo `email_sender.py` y pegar este código:

```python
import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Permisos requeridos para la API de Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_google_services():
    """
    Crea las credenciales y el servicio de Gmail a partir de las variables de entorno.
    """
    try:
        # Reconstruye la información de las credenciales
        creds_info = {
            'client_id': os.environ.get('GMAIL_CLIENT_ID'),
            'client_secret': os.environ.get('GMAIL_CLIENT_SECRET'),
            'refresh_token': os.environ.get('GMAIL_REFRESH_TOKEN'),
            'token_uri': 'https://oauth2.googleapis.com/token',
        }

        if not all(creds_info.values()):
            print("Error: Faltan una o más variables de entorno de Gmail.")
            return None

        creds = Credentials.from_authorized_user_info(creds_info, SCOPES)

        # Si las credenciales han expirado, las refresca.
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        # Construye el servicio de Gmail
        gmail_service = build('gmail', 'v1', credentials=creds)
        return gmail_service

    except Exception as e:
        print(f"Ocurrió un error al crear los servicios de Google: {e}")
        return None

def send_email(gmail_service, sender_email, recipient_email, subject, body):
    """
    Crea y envía un correo simple (sin adjuntos) usando la API de Gmail.
    """
    try:
        message = MIMEMultipart()
        message['to'] = recipient_email
        message['from'] = sender_email
        message['subject'] = subject

        # Usa 'html' para permitir formato en el cuerpo del correo
        msg = MIMEText(body, 'html')
        message.attach(msg)

        # La API de Gmail requiere que el mensaje esté codificado en base64-urlsafe.
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        # 'me' se refiere al usuario autenticado
        send_message = gmail_service.users().messages().send(
            userId='me', 
            body=create_message
        ).execute()
        
        print(f"Correo enviado a {recipient_email}. Message ID: {send_message['id']}")
        return True

    except HttpError as error:
        print(f"Ocurrió un error al enviar el correo con la API de Gmail: {error}")
        return False
    except Exception as e:
        print(f"Ocurrió un error inesperado al crear el mensaje: {e}")
        return False

# --- Ejemplo de Uso ---
if __name__ == '__main__':
    gmail_service = get_google_services()
    
    if gmail_service:
        sender = os.environ.get("SENDER_EMAIL")
        recipient = "email_del_destinatario@ejemplo.com" # Cambia esto
        
        asunto = "Asunto de prueba desde Python"
        cuerpo = "<h1>¡Hola!</h1><p>Este es un correo de prueba enviado con la API de Gmail.</p>"
        
        send_email(gmail_service, sender, recipient, asunto, cuerpo)

```

### Resumen del Flujo

1.  `get_google_services()` lee las variables de entorno, reconstruye las credenciales y las usa para autenticarse con Google. Si el token de acceso ha expirado, usa el `refresh_token` para obtener uno nuevo.
2.  `send_email()` toma el servicio de Gmail autenticado y los detalles del correo, lo formatea como un mensaje MIME y lo envía a través de la API.
3.  El bloque `if __name__ == '__main__':` muestra cómo llamar a estas funciones para enviar un correo de prueba.

¡Y eso es todo! Con estos pasos, puedes integrar el envío de correos de Gmail en cualquier otro proyecto de Python.
