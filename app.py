import os
import io
import base64
import time
import hashlib
from supabase import create_client
import qrcode
import random
import numpy as np
import secrets
from flask import Flask, render_template, request, send_file, redirect
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
import fitz  # PyMuPDF
from qreader import QReader

# --- CONFIGURACIÓN DE SUPABASE ---
SUPABASE_URL = "https://xyjycsnxbcutwwelrogz.supabase.co"
SUPABASE_KEY = "sb_secret_3bq1DNAwQdU3yNN8_-iHCw_jMchEnqX" # La que empieza con 'sb_secret'
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
# Variable para guardar el recorte y que no se pierda al descargar
ultimo_recorte_qr = None
peticiones_en_vuelo = {}
# --- CONFIGURACIÓN DE RUTAS ---
FOLDER_FUENTES = "fuentes"
FOLDER_IMAGENES = "imagenes"
# Definimos los posibles fondos
FONDO_TIVE1 = os.path.join("static", "tive.png")
FONDO_TIVE2 = os.path.join("static", "tive2.png")
FONDO_TIVE3 = os.path.join("static", "tive3.png")

# Definición de fuentes
FUENTE_GENERAL = os.path.join(FOLDER_FUENTES, "phagspa.ttf")
FUENTE_ARIAL = os.path.join(FOLDER_FUENTES, "arial.ttf")
FUENTE_ARIALBD = os.path.join(FOLDER_FUENTES, "arialbd.ttf")
FUENTE_ROBOTOBD = os.path.join(FOLDER_FUENTES, "robotobd.ttf")

COLOR_GRIS_73 = (130, 130, 130)  
COLOR_NEGRO = (0, 0, 0)
COLOR_GRISCLARO = (203, 203, 203)
COORD_FOTO = (1159, 2245) 
# Coordenada (X, Y) en tive.png donde se pegará el recorte del PDF
# Esta es la coordenada maestra. Si la cambias aquí, se cambia en todo el sistema.
COORD_PEGADO_PDF = (230, 200)

CONFIG_CAMPOS = {
    "verificacion": (845, 288, 30, None, COLOR_NEGRO), 
    "n_titulo": (670, 331, 30, None, COLOR_NEGRO),
    "fecha": (638, 374, 30, None, COLOR_NEGRO),
    "zona_registral": (187, 689, 34, FUENTE_ARIALBD, COLOR_GRIS_73),
    "sede": (185, 735, 34, FUENTE_ARIALBD, COLOR_GRIS_73),
    "partida": (501, 840, 30, None, COLOR_NEGRO), 
    "dua": (375, 903, 30, None, COLOR_NEGRO),
    "titulo": (321, 966, 30, None, COLOR_NEGRO),
    "fecha_titulo": (485, 1029, 30, None, COLOR_NEGRO),
    "categoria": (383, 1477, 30, None, COLOR_NEGRO),
    "marca": (326, 1527, 30, None, COLOR_NEGRO),
    "modelo": (338, 1576, 30, None, COLOR_NEGRO),
    "color": (311, 1626, 30, None, COLOR_NEGRO),
    "vin": (469, 1676, 30, None, COLOR_NEGRO),
    "serie": (494, 1729, 30, None, COLOR_NEGRO),
    "motor": (499, 1777, 30, None, COLOR_NEGRO),
    "carroceria": (399, 1827, 30, None, COLOR_NEGRO),
    "potencia": (362, 1877, 30, None, COLOR_NEGRO),
    "form_rod": (397, 1927, 30, None, COLOR_NEGRO),
    "combustible": (425, 1975, 30, None, COLOR_NEGRO),
    "asientos": (390, 2039, 30, None, COLOR_NEGRO),
    "pasajeros": (390, 2088, 30, None, COLOR_NEGRO),
    "ruedas": (390, 2141, 30, None, COLOR_NEGRO),
    "ejes": (390, 2189, 30, None, COLOR_NEGRO),
    "cilindros": (751, 2039, 30, None, COLOR_NEGRO),
    "longitud": (751, 2088, 30, None, COLOR_NEGRO),
    "altura": (751, 2141, 30, None, COLOR_NEGRO),
    "ancho": (751, 2189, 30, None, COLOR_NEGRO),
    "cilindrada": (1242, 2039, 30, None, COLOR_NEGRO),
    "p_bruto": (1242, 2088, 30, None, COLOR_NEGRO),
    "p_neto": (1242, 2141, 30, None, COLOR_NEGRO),
    "carga_util": (1242, 2189, 30, None, COLOR_NEGRO),
    "año_modelo": (1413, 1527, 30, None, COLOR_NEGRO),
    "año_fabricacion": (1413, 1476, 30, None, COLOR_NEGRO), # Ejemplo de coordenada
    "version": (1028, 1927, 30, None, COLOR_NEGRO),
    "numero_tarjeta":(1393, 1396, 30, FUENTE_ARIAL, COLOR_GRISCLARO),
    "placa":(1136, 947, 81, FUENTE_ROBOTOBD, COLOR_NEGRO),
    "placa_anterior": (1235, 1150, 30, None, COLOR_NEGRO) # Ejemplo de coordenada   
}

def generar_imagen_pil(texto_input, modo_azura=False):
    lineas = texto_input.split('\n')
    
    # Detectar presencia de datos clave
    tiene_placa_ant = any("placa_anterior:" in l.lower() and l.split(':', 1)[1].strip() for l in lineas)
    tiene_año_fab = any("año_fabricacion:" in l.lower() and l.split(':', 1)[1].strip() for l in lineas)

    # Selección de fondo: Si modo_azura es True, forzamos TIVE1
    if modo_azura:
        ruta_fondo = FONDO_TIVE1
    elif tiene_placa_ant:
        ruta_fondo = FONDO_TIVE3
    elif tiene_año_fab:
        ruta_fondo = FONDO_TIVE2
    else:
        ruta_fondo = FONDO_TIVE1

    if not os.path.exists(ruta_fondo): 
        print(f"Error: No se encuentra el archivo {ruta_fondo}")
        return None

    img = Image.open(ruta_fondo).convert("RGB")
    draw = ImageDraw.Draw(img)
    for linea in lineas:
        if "foto:" in linea.lower():
            depto_folder = linea.split(':', 1)[1].strip()
            ruta_carpeta = os.path.join(FOLDER_IMAGENES, depto_folder) 
            if os.path.exists(ruta_carpeta) and os.path.isdir(ruta_carpeta):
                archivos = [f for f in os.listdir(ruta_carpeta) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                if archivos:
                    foto_elegida = random.choice(archivos)
                    ruta_foto = os.path.join(ruta_carpeta, foto_elegida)
                    foto_img = Image.open(ruta_foto).convert("RGBA")
                    img.paste(foto_img, COORD_FOTO, foto_img)
    for linea in lineas:
        if ":" in linea:
            partes = linea.split(':', 1)
            etiqueta = partes[0].strip().lower()
            valor_raw = partes[1].strip()
            
            # Si el valor contiene 'tn' o 'mt', no lo pasamos a mayúsculas totalmente
            if any(unit in valor_raw.lower() for unit in ['tn', 'mt']):
                valor = valor_raw # Mantiene el valor como viene del JS (ej: "0.199 tn")
            else:
                valor = valor_raw.upper()
            if etiqueta in CONFIG_CAMPOS and valor.strip() != "":
                x, y, tam, fuente_especifica, color = CONFIG_CAMPOS[etiqueta]
                
                x, y, tam, fuente_especifica, color = CONFIG_CAMPOS[etiqueta]
                ruta_fuente = fuente_especifica if fuente_especifica else FUENTE_GENERAL
                try:
                    fuente = ImageFont.truetype(ruta_fuente, tam)
                    draw.text((x, y), valor, font=fuente, fill=color, anchor="lt")
                except:
                    fuente = ImageFont.truetype(FUENTE_GENERAL, tam)
                    draw.text((x, y), valor, font=fuente, fill=color, anchor="lt")
    return img


def extraer_recorte_pdf(pdf_stream):
    try:
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        pagina = doc[0]
        
        # 1. Intento con IA (Mejorado para SUNARP)
        qreader = QReader(model_size='m')
        # Renderizamos a zoom 4 para buscar
        pix_busqueda = pagina.get_pixmap(matrix=fitz.Matrix(4, 4))
        img_busqueda = Image.frombytes("RGB", [pix_busqueda.width, pix_busqueda.height], pix_busqueda.samples)
        
        # Mejoramos contraste para que la IA vea mejor el QR
        img_pre = ImageOps.grayscale(img_busqueda)
        img_pre = ImageEnhance.Contrast(img_pre).enhance(2.0)
        
        detecciones = qreader.detect_and_decode(image=np.array(img_pre.convert("RGB")), return_detections=True)
        
        if detecciones and len(detecciones) > 0:
            det = detecciones[0]
            bbox = det.get('bbox_xyxy') if isinstance(det, dict) else getattr(det, 'bbox_xyxy', None)
            
            if bbox is not None:
                padding = 12
                # Ajustamos las coordenadas (dividido por 4 del zoom de búsqueda)
                rect_final = fitz.Rect((bbox[0]/4)-padding, (bbox[1]/4)-padding, (bbox[2]/4)+padding, (bbox[3]/4)+padding)
                print("DEBUG: QR Detectado por IA")
            else:
                # Si falla el bbox, usamos zona fija
                rect_final = fitz.Rect(45, 40, 120, 115) 
        else:
            # Zona fija por defecto para el formato de placa ART-314
            rect_final = fitz.Rect(45, 40, 120, 115)
            print("DEBUG: Usando zona fija (IA no detectó)")

        # 2. Generar el recorte de alta calidad
        zoom_final = 4.29
        pix_recorte = pagina.get_pixmap(clip=rect_final, matrix=fitz.Matrix(zoom_final, zoom_final))
        img_recorte = Image.frombytes("RGB", [pix_recorte.width, pix_recorte.height], pix_recorte.samples)
        
        doc.close()
        return img_recorte
    except Exception as e:
        print(f"Error en extraer_recorte_pdf: {e}")
        return None
    
#[cite: 3] Versión con persistencia de datos de Azura
@app.route('/', methods=['GET', 'POST'])
def index():
    global ultimo_recorte_qr
    imagen_base64, texto_previo, depto_previo, pos_guion = None, "", "", "cen"
    edit_az, az_verif, az_fecha, az_tarjeta = "NO", "", "", ""
    
    if request.method == 'POST':
        texto_previo = request.form.get('texto_datos', '')
        depto_previo = request.form.get('depto_nombre', '')
        pos_guion = request.form.get('pos_guion', 'cen')
        edit_az = request.form.get('edit_az', 'NO')
        az_verif = request.form.get('az_verif_val', '')
        az_fecha = request.form.get('az_fecha_val', '')
        az_tarjeta = request.form.get('az_tarjeta_val', '')
        
        modo_azura = (edit_az == "SI")
        img = generar_imagen_pil(texto_previo, modo_azura=modo_azura)
        
        if img:
            # 1. GENERAR QR SOLO PARA VISTA PREVIA
            url_temp = f"https://publicidad-certificada.sunarpgobpe.site/ver/{secrets.token_hex(4)}"
            
            qr = qrcode.QRCode(version=5, box_size=10, border=1)
            qr.add_data(url_temp)
            qr.make(fit=True)
            qr_img_temp = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
            
            # --- CALIBRACIÓN DE TAMAÑO EXACTO ---
            # Cambia estos números (250, 250) para ajustar el tamaño píxel por píxel
            tamano_qr = (250, 250) 
            qr_img = qr_img_temp.resize(tamano_qr, Image.Resampling.LANCZOS)
            
            # Pegar QR en la imagen
            img.paste(qr_img, COORD_PEGADO_PDF)
            ultimo_recorte_qr = qr_img

            # 2. MOSTRAR SOLO VISTA PREVIA (No se guarda en Supabase aquí)
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=90)
            imagen_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
    return render_template('index.html', 
                           imagen_preview=imagen_base64, 
                           texto=texto_previo, 
                           depto_previo=depto_previo, 
                           pos_guion=pos_guion,
                           edit_az=edit_az, 
                           az_verif=az_verif, 
                           az_fecha=az_fecha, 
                           az_tarjeta=az_tarjeta)

@app.route('/descargar', methods=['POST'])
def descargar():
    global peticiones_en_vuelo
    
    texto = request.form.get('texto_datos', '')
    # Creamos una huella única basada en el texto para identificar la petición
    huella = hashlib.md5(texto.encode()).hexdigest()
    ahora = time.time()

    # BLOQUEO ANTIDUPLICADO: Si se envió lo mismo hace menos de 7 segundos, ignorar
    if huella in peticiones_en_vuelo:
        if ahora - peticiones_en_vuelo[huella] < 7:
            print("⚠️ Bloqueo de ráfaga: Petición duplicada detectada.")
            return "", 204 # Respuesta "No Content" para que el navegador no haga nada

    peticiones_en_vuelo[huella] = ahora

    # --- Inicia proceso normal ---
    edit_az = request.form.get('edit_az', 'NO')
    placa = "S-P"
    for linea in texto.split('\n'):
        if linea.lower().startswith('placa:'):
            placa = linea.split(':')[1].strip().upper()
            break
    
    img = generar_imagen_pil(texto, modo_azura=(edit_az == "SI"))
    
    if img:
        id_final = secrets.token_hex(16).upper()
        url_final = f"https://publicidad-certificada.sunarpgobpe.site/servicio/verCertificado/{id_final}"
        
        qr = qrcode.QRCode(version=5, box_size=10, border=1)
        qr.add_data(url_final)
        qr.make(fit=True)
        qr_def_temp = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        qr_definitivo = qr_def_temp.resize((250, 250), Image.Resampling.LANCZOS)
        img.paste(qr_definitivo, COORD_PEGADO_PDF)

        pdf_io = io.BytesIO()
        try:
            img.convert("RGB").save(pdf_io, 'PDF', resolution=300.0)
            pdf_bytes = pdf_io.getvalue()
            pdf_io.seek(0)

            # SUBIDA A SUPABASE
            nombre_nube = f"TIVE_{id_final}.pdf"
            supabase.storage.from_('reportes').upload(
                path=nombre_nube,
                file=pdf_bytes,
                file_options={"content-type": "application/pdf", "x-upsert": "false"}
            )
            print(f"✅ Archivo único guardado: {nombre_nube}")
        except Exception as e:
            if "already exists" in str(e):
                print("⚠️ Supabase evitó un duplicado.")
            else:
                print(f"❌ Error: {e}")

        # Limpiar diccionario de peticiones viejas para ahorrar memoria
        peticiones_en_vuelo = {k: v for k, v in peticiones_en_vuelo.items() if ahora - v < 60}

        return send_file(
            pdf_io, 
            mimetype='application/pdf', 
            as_attachment=True, 
            download_name=f'TIVE_{placa}.pdf'
        )
    
    return "Error", 500

@app.route('/servicio/verCertificado/<id_final>')
def ver_certificado(id_final):
    nombre_archivo = f"TIVE_{id_final}.pdf"
    try:
        # 1. Obtener la URL pública del archivo desde Supabase
        # Asegúrate de que el bucket 'reportes' sea público en la consola de Supabase
        res = supabase.storage.from_('reportes').get_public_url(nombre_archivo)
        
        # 2. Redirigir al usuario directamente al archivo en la nube
        # Esto forzará la visualización o descarga dependiendo del navegador
        return redirect(res, code=302)
    except Exception as e:
        return f"Error al recuperar el certificado: {str(e)}", 404

if __name__ == '__main__':
    app.run(debug=True)