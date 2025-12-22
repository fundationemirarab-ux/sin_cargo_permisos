from flask import Flask, render_template, jsonify, request, send_file
import os
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import io
import re
import math
import json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIÓN ---
# Permisos para Sheets, Drive, y ahora Gmail
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

SPREADSHEET_ID = '1dn9W-1hxSxPmnUUHDbF_ZG_yzaYlOYFoIO3LqDMGgQw'
RANGE_NAME = 'permisos!A2:M'
DRIVE_FOLDER_ID = '1ljOYPhde0Uu9_0l9ToPF8xP4ck2u-3ee'


# --- HELPERS ---
def get_google_services():
    """Crea las credenciales desde las variables de entorno y devuelve los servicios de Google."""
    try:
        # Reconstruye la información de las credenciales a partir de las variables de entorno
        creds_info = {
            'client_id': os.environ.get('GMAIL_CLIENT_ID'),
            'client_secret': os.environ.get('GMAIL_CLIENT_SECRET'),
            'refresh_token': os.environ.get('GMAIL_REFRESH_TOKEN'),
            'token_uri': 'https://oauth2.googleapis.com/token',
        }

        if not all([creds_info['client_id'], creds_info['client_secret'], creds_info['refresh_token']]):
            print("Error: Faltan una o más variables de entorno de Gmail (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN).")
            return None

        # Crea el objeto de credenciales
        creds = Credentials.from_authorized_user_info(creds_info, SCOPES)

        # Si las credenciales han expirado, las refresca. Esto es clave para que no expire la sesión.
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        # Construir los servicios
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        gmail_service = build('gmail', 'v1', credentials=creds)
        
        return {'sheets': sheets_service, 'drive': drive_service, 'gmail': gmail_service}

    except Exception as e:
        print(f"Ocurrió un error al crear los servicios de Google: {e}")
        return None

def download_pdf(drive_service, file_id):
    """Descarga un archivo PDF de Google Drive y devuelve su contenido."""
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
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

def send_email_with_attachment(gmail_service, sender_email, recipient_email, subject, body, attachment_content, attachment_filename):
    """Crea y envía un correo con adjunto usando la API de Gmail."""
    try:
        message = MIMEMultipart()
        message['to'] = recipient_email
        message['from'] = sender_email
        message['subject'] = subject

        msg = MIMEText(body, 'html') # Usar HTML para el cuerpo
        message.attach(msg)

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_content)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        message.attach(part)

        # La API de Gmail requiere que el mensaje esté codificado en base64-urlsafe.
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        # 'me' se refiere al usuario autenticado (el dueño del refresh_token)
        send_message = gmail_service.users().messages().send(userId='me', body=create_message).execute()
        print(f"Correo enviado a {recipient_email}. Message ID: {send_message['id']}")
        return True
    except HttpError as error:
        print(f"Ocurrió un error al enviar el correo con la API de Gmail: {error}")
        return False
    except Exception as e:
        print(f"Ocurrió un error inesperado al crear el mensaje de correo: {e}")
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
        return jsonify({"error": "No se pudo autenticar con Google. Revisa las variables de entorno."}), 500
    
    try:
        sheet = services['sheets'].spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        if not values:
            return jsonify({"records": [], "total_pages": 0, "current_page": 1})

        data = []
        for i, row in enumerate(values):
            data.append({
                'row_index': i + 2,
                'nombre': row[0] if len(row) > 0 else '',
                'apellido': row[1] if len(row) > 1 else '',
                'email': row[5] if len(row) > 5 else '',
                'foto1': row[10] if len(row) > 10 else '',
                'foto2': row[11] if len(row) > 11 else '',
                'status': row[12] if len(row) > 12 else ''
            })
        
        for record in data:
            record['foto1'] = transform_drive_link(record['foto1'])
            record['foto2'] = transform_drive_link(record['foto2'])

        data.reverse()
        
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
        return jsonify({"error": f"Ocurrió un error en la API de Sheets: {error.resp.status}, {error.resp.reason}"}), 500

@app.route('/api/send-sheet-email', methods=['POST'])
def send_sheet_email():
    """Busca un PDF en Drive, y lo envía por correo usando la API de Gmail."""
    data = request.json
    row_index = data.get('row_index')
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    email = data.get('email')

    if not all([row_index, nombre, apellido, email]):
        return jsonify({"status": "error", "message": "Faltan datos en la solicitud."}), 400

    services = get_google_services()
    if not services:
        return jsonify({"status": "error", "message": "No se pudo autenticar con Google. Revisa las variables de entorno."}), 500

    try:
        drive_service = services['drive']
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
        if not sender_email:
            return jsonify({"status": "error", "message": "Falta la variable de entorno SENDER_EMAIL."}), 500
        
        subject = f"Permiso de Pesca adjunto para {nombre} {apellido}"
        body = f"Estimado/a {nombre} {apellido},<br><br>Adjunto encontrará el permiso de pesca solicitado.<br><br>Saludos cordiales."

        if send_email_with_attachment(services['gmail'], sender_email, email, subject, body, pdf_content, pdf_file.get('name')):
            try:
                sheets_service = services['sheets']
                update_range = f'permisos!M{row_index}'
                update_body = { 'values': [['Enviado']] }
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, 
                    range=update_range,
                    valueInputOption='RAW', 
                    body=update_body
                ).execute()
                print(f"Estado de la fila {row_index} actualizado a 'Enviado'.")
            except HttpError as sheet_error:
                print(f"Error al actualizar la hoja: {sheet_error}")
                return jsonify({"status": "success", "message": f"Correo enviado, pero falló al actualizar el estado en la hoja: {sheet_error}"})
            
            return jsonify({"status": "success", "message": f"Correo enviado a {email} y estado actualizado."})
        else:
            return jsonify({"status": "error", "message": "Fallo al enviar el correo a través de la API de Gmail."}), 500

    except Exception as e:
        print(f"Ocurrió un error inesperado en send_sheet_email: {e}")
        return jsonify({"error": "Error interno del servidor al procesar la solicitud."}), 500

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