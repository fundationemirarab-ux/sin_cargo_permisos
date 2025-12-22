from flask import Flask, render_template, jsonify, request, send_file
import os
import google.auth
from google.oauth2 import service_account # Importante para cuentas de servicio
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import io
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re
import math
import json # Importar json
from dotenv import load_dotenv

load_dotenv() # Cargar variables de entorno del archivo .env

app = Flask(__name__)

# --- CONFIGURACIÓN ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

SPREADSHEET_ID = '1dn9W-1hxSxPmnUUHDbF_ZG_yzaYlOYFoIO3LqDMGgQw'
RANGE_NAME = 'permisos!A2:M'
DRIVE_FOLDER_ID = '1ljOYPhde0Uu9_0l9ToPF8xP4ck2u-3ee'


# --- HELPERS ---
def get_google_services():
    """Autentica con las APIs de Google usando una cuenta de servicio."""
    # Las credenciales se cargan desde una variable de entorno en formato JSON para producción (Render)
    # o desde un archivo 'service_account.json' para desarrollo local.
    creds = None
    creds_json_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')

    if creds_json_str:
        try:
            # Producción: Cargar desde variable de entorno
            creds_info = json.loads(creds_json_str)
            creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        except Exception as e:
            print(f"Error al cargar credenciales desde GOOGLE_CREDENTIALS_JSON: {e}")
            return None
    elif os.path.exists('service_account.json'):
        try:
            # Desarrollo local: Cargar desde archivo
            creds = service_account.Credentials.from_service_account_file(
                'service_account.json', scopes=SCOPES)
        except Exception as e:
            print(f"Error al cargar credenciales desde service_account.json: {e}")
            return None
    else:
        # Si no hay credenciales, no se puede continuar
        print("Error: No se encontró 'service_account.json' ni la variable de entorno 'GOOGLE_CREDENTIALS_JSON'.")
        return None

    try:
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return {'sheets': sheets_service, 'drive': drive_service}
    except HttpError as error:
        print(f"Ocurrió un error al crear los servicios de Google: {error}")
        return None

def download_pdf(drive_service, file_id):
    """Descarga un archivo PDF de Google Drive y devuelve su contenido."""
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

def transform_drive_link(link):
    """Transforma un enlace de Google Drive para compartir en un enlace de visualización directa."""
    if not link or 'drive.google.com' not in link:
        return link
    
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', link)
    if match:
        file_id = match.group(1)
        return f'https://drive.google.com/uc?export=view&id={file_id}'
    return link

def send_email_with_attachment(sender_email, sender_password, recipient_email, subject, body, attachment_content, attachment_filename):
    """Envía un correo electrónico con un archivo adjunto."""
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_content)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error al enviar el correo: {e}")
        return False

# --- ENDPOINTS DE LA APP ---

@app.route('/')
def index():
    """Renderiza la página principal."""
    return render_template('index.html')

@app.route('/api/get-sheet-data')
def get_sheet_data():
    """Endpoint para leer los datos de la hoja de cálculo con paginación."""
    services = get_google_services()
    if not services:
        return jsonify({"error": "No se pudo autenticar con Google."}), 500
    
    try:
        sheet = services['sheets'].spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        if not values:
            return jsonify({"records": [], "total_pages": 0, "current_page": 1})

        data = []
        for i, row in enumerate(values):
            data.append({
                'row_index': i + 2, # Fila real en la hoja de cálculo
                'nombre': row[0] if len(row) > 0 else '',
                'apellido': row[1] if len(row) > 1 else '',
                'email': row[5] if len(row) > 5 else '', # Columna F (indice 5)
                'foto1': row[10] if len(row) > 10 else '', # Columna K (indice 10)
                'foto2': row[11] if len(row) > 11 else '', # Columna L (indice 11)
                'status': row[12] if len(row) > 12 else '' # Columna M (indice 12)
            })
        
        for record in data:
            record['foto1'] = transform_drive_link(record['foto1'])
            record['foto2'] = transform_drive_link(record['foto2'])

        # Invertir el orden de toda la lista para que los más nuevos aparezcan primero
        data.reverse()
        
        # Implementación de la paginación
        page = request.args.get('page', 1, type=int)
        PAGE_SIZE = 10
        
        start_index = (page - 1) * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        
        paged_records = data[start_index:end_index]
        total_pages = math.ceil(len(data) / PAGE_SIZE)

        return jsonify({
            "records": paged_records,
            "total_pages": total_pages,
            "current_page": page
        })

    except HttpError as error:
        print(f"Ocurrió un error en la API de Sheets: {error}")
        return jsonify({"error": f"Ocurrió un error en la API de Sheets: {error}"}), 500


@app.route('/api/send-sheet-email', methods=['POST'])
def send_sheet_email():
    """Busca un PDF en Drive, y lo envía por correo a la dirección de una fila."""
    data = request.json
    row_index = data.get('row_index')
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    email = data.get('email')

    if not all([row_index, nombre, apellido, email]):
        return jsonify({"status": "error", "message": "Faltan datos en la solicitud."}), 400

    services = get_google_services()
    if not services:
        return jsonify({"status": "error", "message": "No se pudo autenticar con Google."}), 500

    try:
        drive_service = services['drive']
        # Construir la consulta de búsqueda para Drive
        query = f"'{DRIVE_FOLDER_ID}' in parents and name contains '{nombre}' and name contains '{apellido}' and mimeType='application/pdf'"
        
        
        results = drive_service.files().list(q=query, pageSize=2, fields="files(id, name)").execute()
        files = results.get('files', [])

        if len(files) == 0:
            return jsonify({"status": "error", "message": f"No se encontró ningún PDF para '{nombre} {apellido}'."}), 404
        if len(files) > 1:
            return jsonify({"status": "error", "message": f"Se encontraron múltiples PDFs para '{nombre} {apellido}'. No se puede decidir cuál enviar."}), 409

        pdf_file = files[0]
        pdf_content = download_pdf(drive_service, pdf_file['id'])
        
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")

        if not sender_email or not sender_password:
            return jsonify({"status": "error", "message": "Faltan credenciales de envío de correo en el servidor."}), 500
        
        subject = f"Permiso de Pesca adjunto para {nombre} {apellido}"
        body = f"Estimado/a {nombre} {apellido},\n\nAdjunto encontrará el permiso de pesca solicitado.\n\nSaludos cordiales."

        if send_email_with_attachment(sender_email, sender_password, email, subject, body, pdf_content, pdf_file.get('name')):
            try:
                sheets_service = services['sheets']
                update_range = f'permisos!M{row_index}' # Columna M para el estado
                update_body = {
                    'values': [['Enviado']]
                }
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, 
                    range=update_range,
                    valueInputOption='RAW', 
                    body=update_body
                ).execute()
                print(f"Estado de la fila {row_index} actualizado a 'Enviado' en la hoja de cálculo.")
            except HttpError as sheet_error:
                print(f"Error al actualizar la hoja de cálculo para la fila {row_index}: {sheet_error}")
                return jsonify({"status": "error", "message": f"Correo enviado, pero fallo al actualizar el estado en la hoja: {sheet_error}"}), 500
            
            return jsonify({"status": "success", "message": f"Correo enviado a {email} y estado actualizado en la hoja."})
        else:
            return jsonify({"status": "error", "message": "Fallo al enviar el correo."}), 500

    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
        return jsonify({"error": f"Error interno del servidor: {e}"}), 500


@app.route('/api/download-pdf-by-name/<nombre>/<apellido>')
def download_pdf_by_name(nombre, apellido):
    """Busca un PDF en Drive por nombre/apellido y lo devuelve para descargar."""
    services = get_google_services()
    if not services:
        return "No se pudo autenticar con Google.", 500

    try:
        drive_service = services['drive']
        query = f"'{DRIVE_FOLDER_ID}' in parents and name contains '{nombre}' and name contains '{apellido}' and mimeType='application/pdf'"
        
        results = drive_service.files().list(q=query, pageSize=2, fields="files(id, name)").execute()
        files = results.get('files', [])

        if len(files) == 0:
            return f"No se encontró ningún PDF para '{nombre} {apellido}'.", 404
        if len(files) > 1:
            return f"Se encontraron múltiples PDFs para '{nombre} {apellido}'. No se puede decidir cuál descargar.", 409

        pdf_file = files[0]
        pdf_content = download_pdf(drive_service, pdf_file['id'])
        
        return send_file(
            io.BytesIO(pdf_content),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=pdf_file.get('name')
        )

    except HttpError as error:
        print(f"Ocurrió un error en la API de Google al descargar: {error}")
        return "Error de la API de Google al descargar el archivo.", 500
    except Exception as e:
        print(f"Ocurrió un error inesperado al descargar: {e}")
        return "Error interno del servidor al descargar el archivo.", 500


if __name__ == '__main__':
    app.run(debug=True, port=5001)
