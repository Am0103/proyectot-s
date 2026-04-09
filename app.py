from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import csv
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = "clave_secreta"

# Usuarios y archivos por cliente con ROLES
CLIENTES = {
    "bulevar": {
        "usuarios": {
            "bulevar": {"clave": "admin", "rol": "editor"},
            "bulevar_view": {"clave": "view123", "rol": "viewer"}
        },
        "csv": "1/dispositivos1.csv",
        "camaras_csv": "1/camaras1.csv"
    },
    "eden": {
        "usuarios": {
            "eden": {"clave": "admin", "rol": "editor"},
            "eden_view": {"clave": "view123", "rol": "viewer"}
        },
        "csv": "1/dispositivos2.csv",
        "camaras_csv": "1/camaras2.csv"
    }
}

# Usuario administrador
ADMIN = {"usuario": "admin", "clave": "admin123"}

# Archivo de log
LOG_FILE = "cambios_log.json"

def log_cambio(cliente, usuario, accion, detalle=""):
    """Registra un cambio en el log"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        
        nuevo_log = {
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "cliente": cliente,
            "usuario": usuario,
            "accion": accion,
            "detalle": detalle
        }
        
        logs.append(nuevo_log)
        logs = logs[-100:]
        
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"Error guardando log: {e}")

def guardar_mensaje_contacto(nombre, empresa, email, telefono, servicio, mensaje, newsletter=False):
    """Guarda un mensaje de contacto en archivo CSV"""
    archivo_contactos = "contactos.csv"
    
    try:
        # Crear encabezados si el archivo no existe
        if not os.path.exists(archivo_contactos):
            with open(archivo_contactos, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Fecha', 'Hora', 'Nombre', 'Empresa', 'Email', 'Telefono', 'Servicio', 'Mensaje', 'Newsletter', 'Estado'])
        
        # Agregar nuevo mensaje
        with open(archivo_contactos, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            ahora = datetime.now()
            writer.writerow([
                ahora.strftime("%d/%m/%Y"),
                ahora.strftime("%H:%M:%S"),
                nombre,
                empresa if empresa else "No especificada",
                email,
                telefono if telefono else "No especificado",
                servicio if servicio else "Consulta general",
                mensaje,
                "Sí" if newsletter else "No",
                "Nuevo"
            ])
        
        print(f"✅ Mensaje de contacto guardado: {nombre} - {email}")
    
    except Exception as e:
        print(f"❌ Error guardando mensaje de contacto: {e}")
        raise

# ========== RUTAS DE LANDING PAGE ==========

@app.route("/")
def home():
    """Página principal de la empresa"""
    print("🏠 Acceso a página principal")
    return render_template("landing/home.html")

@app.route("/servicios")
def servicios():
    """Página de servicios"""
    print("⚙️ Acceso a página de servicios")
    return render_template("landing/servicios.html")

@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    """Página de contacto"""
    if request.method == "POST":
        # Procesar formulario de contacto
        try:
            # Obtener datos del formulario
            nombre = request.form.get("nombre", "").strip()
            empresa = request.form.get("empresa", "").strip()
            email = request.form.get("email", "").strip()
            telefono = request.form.get("telefono", "").strip()
            servicio = request.form.get("servicio", "").strip()
            mensaje = request.form.get("mensaje", "").strip()
            consentimiento = request.form.get("consentimiento") == "on"
            newsletter = request.form.get("newsletter") == "on"
            
            # Validar campos obligatorios
            if not nombre or not email or not mensaje:
                return jsonify({
                    "success": False, 
                    "message": "Faltan campos obligatorios (nombre, email, mensaje)"
                })
            
            # Validar consentimiento RGPD
            if not consentimiento:
                return jsonify({
                    "success": False, 
                    "message": "Debe aceptar la Política de Privacidad para continuar"
                })
            
            # Guardar en CSV
            guardar_mensaje_contacto(nombre, empresa, email, telefono, servicio, mensaje, newsletter)
            
            print(f"📧 Nuevo mensaje de contacto de: {nombre} ({email})")
            
            return jsonify({
                "success": True, 
                "message": "¡Gracias por tu mensaje! Nos pondremos en contacto contigo pronto."
            })
        
        except Exception as e:
            print(f"❌ Error al procesar contacto: {e}")
            return jsonify({
                "success": False, 
                "message": "Error al enviar el mensaje. Inténtalo de nuevo."
            })
    
    # GET request - mostrar formulario
    print("📧 Acceso a página de contacto")
    return render_template("landing/contacto.html")

@app.route("/proyectos")
def proyectos():
    """Página de proyectos"""
    print("🚀 Acceso a página de proyectos")
    return render_template("landing/proyectos.html")

@app.route("/privacidad")
def privacidad():
    """Página de política de privacidad"""
    print("🔒 Acceso a página de privacidad")
    return render_template("landing/privacidad.html")

# ========== RUTAS DEL SISTEMA DE GESTIÓN ==========

@app.route("/sistema/")
def sistema_home():
    """Redirige al login del sistema"""
    print("🔐 Acceso al sistema - redirigiendo a login")
    return redirect(url_for("sistema_login"))

@app.route("/sistema/login", methods=["GET", "POST"])
def sistema_login():
    """Login del sistema de gestión"""
    print(f"🔐 Acceso a login del sistema - Método: {request.method}")
    
    if request.method == "POST":
        cliente = request.form.get("cliente")
        usuario = request.form.get("usuario")
        clave = request.form.get("clave")
        
        print(f"📝 Datos recibidos: cliente={cliente}, usuario={usuario}")
        
        # Verificar si es admin
        if usuario == ADMIN["usuario"] and clave == ADMIN["clave"]:
            print("✅ Login admin exitoso")
            session.clear()
            session["admin"] = True
            session["usuario"] = "Administrador"
            session["rol"] = "admin"
            log_cambio("SISTEMA", "admin", "Inicio de sesión admin")
            print("🔧 Redirigiendo a admin panel")
            return redirect(url_for("admin_panel"))
        
        # Verificar cliente normal
        if cliente in CLIENTES:
            usuarios_cliente = CLIENTES[cliente]["usuarios"]
            if usuario in usuarios_cliente and usuarios_cliente[usuario]["clave"] == clave:
                print(f"✅ Login cliente exitoso: {cliente}/{usuario}")
                session.clear()
                session["cliente"] = cliente
                session["usuario"] = usuario
                session["rol"] = usuarios_cliente[usuario]["rol"]
                log_cambio(cliente, usuario, f"Inicio de sesión ({session['rol']})")
                print("📊 Redirigiendo a index")
                return redirect(url_for("index"))
        
        print("❌ Credenciales incorrectas")
        return render_template("sistema/login.html", error="Usuario/clave incorrectos", clientes=CLIENTES.keys())
    
    print("📋 Mostrando formulario de login")
    return render_template("sistema/login.html", clientes=CLIENTES.keys())

@app.route("/sistema/panel")
def index():
    """Panel principal del sistema"""
    print("📊 Acceso a panel del sistema")
    print(f"� Sesión: {dict(session)}")
    
    if "usuario" not in session:
        print("❌ No hay usuario, redirigiendo a login")
        return redirect(url_for("sistema_login"))
    
    if session.get("admin"):
        print("🔧 Admin detectado, redirigiendo a admin")
        return redirect(url_for("admin_panel"))
    
    cliente = session.get("cliente", "")
    rol = session.get("rol", "viewer")
    print(f"✅ Mostrando panel para: {cliente} ({rol})")
    return render_template("sistema/index.html", cliente=cliente, rol=rol)

# Ruta de compatibilidad - redirige al nuevo login
@app.route("/login")
def login_redirect():
    """Ruta de compatibilidad que redirige al login del sistema"""
    return redirect(url_for("sistema_login"))

@app.route("/logout")
def logout():
    """Cerrar sesión y volver a la página principal"""
    print("🚪 Cerrando sesión")
    print(f"🔍 Sesión antes de cerrar: {dict(session)}")
    
    if session.get("admin"):
        log_cambio("SISTEMA", "admin", "Cierre de sesión admin")
    elif session.get("cliente"):
        log_cambio(session.get("cliente", ""), session.get("usuario", ""), 
                  f"Cierre de sesión ({session.get('rol', '')})")
    
    session.clear()
    return redirect(url_for("home"))  # Redirige a la página principal

# ========== RUTAS DE ADMINISTRACIÓN ==========

@app.route("/admin")
def admin_panel():
    """Panel de administración"""
    print("🔧 Acceso a admin panel")
    print(f"🔍 Sesión: {dict(session)}")
    
    if not session.get("admin"):
        print("❌ No es admin, redirigiendo a login")
        return redirect(url_for("sistema_login"))
    
    print("✅ Mostrando panel de admin")
    return render_template("sistema/admin.html")

@app.route("/api/admin/clientes")
def api_admin_clientes():
    print("📡 API: Solicitud de clientes")
    print(f"🔍 Sesión: {dict(session)}")
    
    if not session.get("admin"):
        print("❌ No autorizado para API admin")
        return jsonify({"error": "No autorizado"}), 401
    
    clientes_info = []
    for nombre_cliente, info in CLIENTES.items():
        for usuario, datos in info["usuarios"].items():
            clientes_info.append({
                "cliente": nombre_cliente,
                "usuario": usuario,
                "clave": datos["clave"],
                "rol": datos["rol"],
                "csv": info["csv"]
            })
    
    print(f"✅ Enviando {len(clientes_info)} usuarios")
    return jsonify(clientes_info)

@app.route("/api/admin/update_usuario", methods=["POST"])
def api_admin_update_usuario():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    req = request.json
    cliente = req.get("cliente")
    usuario = req.get("usuario")
    nueva_clave = req.get("clave")
    nuevo_rol = req.get("rol")
    
    if cliente in CLIENTES and usuario in CLIENTES[cliente]["usuarios"]:
        old_data = CLIENTES[cliente]["usuarios"][usuario].copy()
        CLIENTES[cliente]["usuarios"][usuario]["clave"] = nueva_clave
        CLIENTES[cliente]["usuarios"][usuario]["rol"] = nuevo_rol
        
        log_cambio("SISTEMA", "admin", f"Actualización usuario {cliente}/{usuario}", 
                  f"Rol: {old_data['rol']} -> {nuevo_rol}")
        
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/api/admin/add_usuario", methods=["POST"])
def api_admin_add_usuario():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    req = request.json
    cliente = req.get("cliente")
    nuevo_usuario = req.get("usuario")
    clave = req.get("clave")
    rol = req.get("rol", "viewer")
    
    if cliente in CLIENTES:
        if nuevo_usuario not in CLIENTES[cliente]["usuarios"]:
            CLIENTES[cliente]["usuarios"][nuevo_usuario] = {
                "clave": clave,
                "rol": rol
            }
            
            log_cambio("SISTEMA", "admin", f"Nuevo usuario creado {cliente}/{nuevo_usuario}", 
                      f"Rol: {rol}")
            
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Usuario ya existe"}), 400
    else:
        return jsonify({"error": "Cliente no encontrado"}), 404

@app.route("/api/admin/delete_usuario", methods=["POST"])
def api_admin_delete_usuario():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    req = request.json
    cliente = req.get("cliente")
    usuario = req.get("usuario")
    
    if cliente in CLIENTES and usuario in CLIENTES[cliente]["usuarios"]:
        del CLIENTES[cliente]["usuarios"][usuario]
        
        log_cambio("SISTEMA", "admin", f"Usuario eliminado {cliente}/{usuario}")
        
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Usuario no encontrado"}), 404

@app.route("/api/admin/logs")
def api_admin_logs():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return jsonify(logs[-50:][::-1])
        else:
            return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/contactos")
def api_admin_contactos():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    archivo_contactos = "contactos.csv"
    
    try:
        if not os.path.exists(archivo_contactos):
            return jsonify([])
        
        contactos = []
        encodings = ['utf-8', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(archivo_contactos, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        contactos.append(row)
                break
            except UnicodeDecodeError:
                continue
        
        # Ordenar por fecha/hora más reciente primero
        contactos.reverse()
        
        return jsonify(contactos)
    
    except Exception as e:
        print(f"Error cargando contactos: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/contacto_estado", methods=["POST"])
def api_admin_contacto_estado():
    if not session.get("admin"):
        return jsonify({"error": "No autorizado"}), 401
    
    req = request.json
    email = req.get("email")
    fecha = req.get("fecha")
    hora = req.get("hora")
    nuevo_estado = req.get("estado", "Leído")
    
    archivo_contactos = "contactos.csv"
    
    try:
        if not os.path.exists(archivo_contactos):
            return jsonify({"error": "Archivo no encontrado"}), 404
        
        # Leer todos los contactos
        contactos = []
        with open(archivo_contactos, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Email'] == email and row['Fecha'] == fecha and row['Hora'] == hora:
                    row['Estado'] = nuevo_estado
                contactos.append(row)
        
        # Escribir de vuelta
        with open(archivo_contactos, 'w', newline='', encoding='utf-8') as f:
            if contactos:
                writer = csv.DictWriter(f, fieldnames=contactos[0].keys())
                writer.writeheader()
                writer.writerows(contactos)
        
        return jsonify({"success": True})
    
    except Exception as e:
        print(f"Error actualizando estado contacto: {e}")
        return jsonify({"error": str(e)}), 500

# ========== RUTAS EXISTENTES ==========

@app.route("/api/data")
def api_data():
    if "cliente" not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    csv_path = CLIENTES[session["cliente"]]["csv"]
    data = []
    
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8-sig']
    
    for encoding in encodings:
        try:
            with open(csv_path, encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    clean_row = {
                        "SERIAL": (row.get("#") or "").strip(),
                        "TIPO": (row.get("TIPO") or "").strip(),
                        "PISO": (row.get("PISO") or "").strip(),
                        "NOMBRE_UBICACION": (row.get("NOMBRE_UBICACION") or "").strip(),
                        "LAZO": (row.get("LAZO") or "").strip(),
                        "DIRECCION": (row.get("DIRECCION") or "").strip(),
                        "FECHA_MANTO": (row.get("FECHA_MANTO") or "").strip(),
                        "ESTADO": (row.get("ESTADO") or "").strip(),
                        "OBSERVACION": (row.get("OBSERVACION") or "").strip()
                    }
                    if clean_row["SERIAL"]:
                        data.append(clean_row)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify(data)

@app.route("/api/update", methods=["POST"])
def api_update():
    if "cliente" not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    if session.get("rol") != "editor":
        return jsonify({"error": "Sin permisos de edición"}), 403
    
    req = request.json
    serial = req.get("SERIAL")
    campo = req.get("campo")
    valor = req.get("valor")
    
    csv_path = CLIENTES[session["cliente"]]["csv"]
    updated = False
    rows = []
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    working_encoding = 'utf-8'
    
    for encoding in encodings:
        try:
            with open(csv_path, encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=";")
                fieldnames = reader.fieldnames
                working_encoding = encoding
                
                for row in reader:
                    if (row.get("#") or "").strip() == serial:
                        old_value = row.get(campo, "")
                        if campo == "SERIAL":
                            row["#"] = valor
                        else:
                            row[campo] = valor
                        row["FECHA_MANTO"] = fecha_hoy
                        updated = True
                        
                        log_cambio(session["cliente"], session["usuario"], 
                                 f"Edición campo {campo}", 
                                 f"ID {serial}: '{old_value}' -> '{valor}'")
                    rows.append(row)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    if updated:
        try:
            with open(csv_path, "w", newline='', encoding=working_encoding) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "No encontrado"}), 404

@app.route("/api/camaras")
def api_camaras():
    if "cliente" not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    camaras_csv = CLIENTES[session["cliente"]]["camaras_csv"]
    data = []
    
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8-sig']
    
    for encoding in encodings:
        try:
            with open(camaras_csv, encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    clean_row = {
                        "SERIAL": (row.get("#") or "").strip(),
                        "UBICACION": (row.get("UBICACION") or "").strip(),
                        "TIPO": (row.get("TIPO") or "").strip(),
                        "ESTADO": (row.get("ESTADO") or "").strip(),
                        "DIAGRAMA": (row.get("DIAGRAMA") or "").strip(),
                        "OBSERVACION": (row.get("OBSERVACION") or "").strip()
                    }
                    if clean_row["SERIAL"]:
                        data.append(clean_row)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify(data)

@app.route("/api/update_camaras", methods=["POST"])
def api_update_camaras():
    if "cliente" not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    if session.get("rol") != "editor":
        return jsonify({"error": "Sin permisos de edición"}), 403
    
    req = request.json
    serial = req.get("SERIAL")
    campo = req.get("campo")
    valor = req.get("valor")
    
    camaras_csv = CLIENTES[session["cliente"]]["camaras_csv"]
    updated = False
    rows = []
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    working_encoding = 'utf-8'
    
    for encoding in encodings:
        try:
            with open(camaras_csv, encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=";")
                fieldnames = reader.fieldnames
                working_encoding = encoding
                
                for row in reader:
                    if (row.get("#") or "").strip() == serial:
                        old_value = row.get(campo, "")
                        if campo == "SERIAL":
                            row["#"] = valor
                        else:
                            row[campo] = valor
                        updated = True
                        
                        log_cambio(session["cliente"], session["usuario"], 
                                 f"Edición cámara {campo}", 
                                 f"ID {serial}: '{old_value}' -> '{valor}'")
                    rows.append(row)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    if updated:
        try:
            with open(camaras_csv, "w", newline='', encoding=working_encoding) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "No encontrado"}), 404

if __name__ == "__main__":
    print("🚀 Iniciando servidor Flask...")
    print("📋 Usuarios configurados:")
    for cliente, info in CLIENTES.items():
        print(f"  🏢 {cliente.upper()}:")
        for user, data in info["usuarios"].items():
            print(f"    👤 {user} / {data['clave']} ({data['rol']})")
    print(f"  🔧 Admin: admin / admin123")
    print("🌐 Servidor disponible en: http://127.0.0.1:5000")
    app.run(debug=True)