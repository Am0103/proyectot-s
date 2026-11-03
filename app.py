from contextlib import contextmanager
from datetime import datetime, timedelta
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile

from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
USERS_FILE = INSTANCE_DIR / "users.json"
BACKUP_DIR = INSTANCE_DIR / "backups"
LOG_FILE = BASE_DIR / "cambios_log.json"
CONTACTS_FILE = BASE_DIR / "contactos.csv"
def load_secret_key():
    configured_key = os.environ.get("TS_SECRET_KEY")
    if configured_key:
        return configured_key

    secret_file = INSTANCE_DIR / "secret_key"
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()

    generated_key = secrets.token_hex(32)
    secret_file.write_text(generated_key, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        app.logger.warning("No fue posible restringir permisos del archivo de clave.")
    app.logger.warning("TS_SECRET_KEY no está definida; se usa una clave local persistente.")
    return generated_key


app.secret_key = load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("TS_COOKIE_SECURE", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=45),
    MAX_CONTENT_LENGTH=1024 * 1024,
)

# Se usan hashes de contraseñas heredadas sólo para migrar las cuentas existentes.
# El acceso inicial obliga a cambiar cada clave antes de usar el sistema.
INITIAL_USERS = {
    "admin": {
        "password_hash": "scrypt:32768:8:1$kgBlFDnFEI7Jjzrx$6050a486cd0638f180ba544ea8ec70f4bc65861dc49d4bbc5032fe7a06108881aee810078f65050246eb763b3363fb389e42cf011834984e9ce095640cd747f9",
        "active": True,
        "must_change_password": True,
    },
    "clients": {
        "bulevar": {
            "bulevar": {
                "password_hash": "scrypt:32768:8:1$lTMlfe8z04tjdule$c0712244dca3aa3eb05f799717dac63956ce0b8ba181935a218532087421a4ef51c81131ca9db25ea2e64a29f526bf7e600d543401375979ceebfd3d44c3a6c2",
                "role": "editor",
                "active": True,
                "must_change_password": True,
            },
            "bulevar_view": {
                "password_hash": "scrypt:32768:8:1$CsNa8IwJlH2AGIJm$9ab8ba7a52bd59c817f613273c02c81a1fdb5909edc79333a22fab67a882e5d558f2999bdab5a9476cf7ca0d5364a255a787ea1fdcdaa1dd37c4b063a3957f06",
                "role": "viewer",
                "active": True,
                "must_change_password": True,
            },
        },
        "eden": {
            "eden": {
                "password_hash": "scrypt:32768:8:1$OLBTbFLcnxcLQU18$60b9a889af0a1a3032a13fd9ea106df143c8cbaba4c62d93d18d58866db14bccdc7b997dbe4ccb14522dcda5064f72a3ae4e5745295cd6a98c39d2363c328767",
                "role": "editor",
                "active": True,
                "must_change_password": True,
            },
            "eden_view": {
                "password_hash": "scrypt:32768:8:1$uKi09UvojOZ0pCJW$37d9a45176ff0976e9aad702d717d80df4ddae3b4dad7785154834839118d88bdcc7ab66cdaaa79c951906aa772f3631346c6a542cc135aa41877935538a95a0",
                "role": "viewer",
                "active": True,
                "must_change_password": True,
            },
        },
    },
}


def save_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def load_users():
    if not USERS_FILE.exists():
        save_json_atomic(USERS_FILE, INITIAL_USERS)
    with USERS_FILE.open(encoding="utf-8") as file:
        users = json.load(file)
    if not isinstance(users, dict) or not isinstance(users.get("clients"), dict):
        raise RuntimeError("El archivo de cuentas de usuario tiene un formato inválido.")
    return users


USERS = load_users()

# Usuarios y archivos por cliente con ROLES
CLIENTES = {
    "bulevar": {
        "csv": BASE_DIR / "1" / "dispositivos1.csv",
        "camaras_csv": BASE_DIR / "1" / "camaras1.csv",
    },
    "eden": {
        "csv": BASE_DIR / "1" / "dispositivos2.csv",
        "camaras_csv": BASE_DIR / "1" / "camaras2.csv",
    },
}


def backup_file(path):
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = BACKUP_DIR / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


@contextmanager
def file_lock(path):
    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            if not lock_file.read(1):
                lock_file.seek(0)
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_csv_file(path, delimiter=";"):
    last_error = None
    for encoding in csv_encodings(path):
        try:
            with path.open(encoding=encoding, newline="") as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                return reader.fieldnames or [], list(reader), encoding
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error or OSError(f"No fue posible leer {path.name}.")


def csv_encodings(path):
    with path.open("rb") as file:
        has_utf8_bom = file.read(3) == b"\xef\xbb\xbf"
    if has_utf8_bom:
        return ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    return ("utf-8", "cp1252", "latin-1")


def write_csv_atomic(path, fieldnames, rows, encoding, delimiter=";"):
    backup_file(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", newline="", encoding=encoding) as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_csv_matrix_atomic(path, matrix, encoding, delimiter=";"):
    backup_file(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", newline="", encoding=encoding) as file:
            csv.writer(file, delimiter=delimiter).writerows(matrix)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def current_revision(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_csv_record(
    path, serial, field, value, allowed_fields, revision, delimiter=";", update_date=False
):
    if not isinstance(serial, str) or not serial.strip() or len(serial) > 120:
        return None, "Identificador inválido", 400
    if not isinstance(field, str):
        return None, "Campo inválido", 400
    if field not in allowed_fields:
        return None, "Campo no permitido", 400
    if not isinstance(value, str) or len(value) > allowed_fields[field]:
        return None, "Valor inválido o demasiado largo", 400
    if not revision:
        return None, "Recarga los datos antes de guardar", 428

    with file_lock(path):
        if not path.exists():
            return None, "Archivo de datos no encontrado", 404
        if current_revision(path) != revision:
            return None, "Los datos cambiaron desde que los cargaste. Recarga antes de guardar.", 409
        for encoding in csv_encodings(path):
            try:
                with path.open(encoding=encoding, newline="") as file:
                    matrix = list(csv.reader(file, delimiter=delimiter))
                break
            except UnicodeDecodeError:
                continue
        else:
            return None, "No fue posible leer el archivo de datos", 500
        if not matrix:
            return None, "El archivo de datos está vacío", 500
        headers = matrix[0]
        try:
            serial_index = headers.index("#")
            field_index = headers.index(field)
        except ValueError:
            return None, "El esquema del archivo no contiene el campo solicitado", 400
        changed_row = None
        for row in matrix[1:]:
            if serial_index < len(row) and row[serial_index].strip() == serial:
                if field_index >= len(row):
                    row.extend([""] * (field_index + 1 - len(row)))
                row[field_index] = value
                if update_date and "FECHA_MANTO" in headers:
                    date_index = headers.index("FECHA_MANTO")
                    if date_index >= len(row):
                        row.extend([""] * (date_index + 1 - len(row)))
                    row[date_index] = datetime.now().strftime("%d/%m/%Y")
                changed_row = row
                break
        if changed_row is None:
            return None, "Registro no encontrado", 404
        write_csv_matrix_atomic(path, matrix, encoding, delimiter=delimiter)
        return current_revision(path), None, 200


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token, "current_year": datetime.now().year}


@app.before_request
def protect_state_changes():
    global USERS
    USERS = load_users()
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        submitted_token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        known_token = session.get("_csrf_token", "")
        if not known_token or not secrets.compare_digest(submitted_token or "", known_token):
            return jsonify({"error": "Token de seguridad inválido. Recarga la página."}), 400


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

def log_cambio(cliente, usuario, accion, detalle=""):
    """Registra un cambio en el log"""
    with file_lock(LOG_FILE):
        if LOG_FILE.exists():
            with LOG_FILE.open(encoding="utf-8") as file:
                logs = json.load(file)
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
        save_json_atomic(LOG_FILE, logs)

def guardar_mensaje_contacto(nombre, empresa, email, telefono, servicio, mensaje, newsletter=False):
    """Guarda un mensaje de contacto en archivo CSV"""
    columns = [
        "Fecha", "Hora", "Nombre", "Empresa", "Email", "Telefono",
        "Servicio", "Mensaje", "Newsletter", "Estado",
    ]
    with file_lock(CONTACTS_FILE):
        if CONTACTS_FILE.exists():
            fieldnames, rows, encoding = read_csv_file(CONTACTS_FILE, delimiter=",")
            columns = fieldnames or columns
        else:
            rows, encoding = [], "utf-8"
        now = datetime.now()
        rows.append({
            "Fecha": now.strftime("%d/%m/%Y"),
            "Hora": now.strftime("%H:%M:%S"),
            "Nombre": nombre,
            "Empresa": empresa or "No especificada",
            "Email": email,
            "Telefono": telefono or "No especificado",
            "Servicio": servicio or "Consulta general",
            "Mensaje": mensaje,
            "Newsletter": "Sí" if newsletter else "No",
            "Estado": "Nuevo",
        })
        write_csv_atomic(CONTACTS_FILE, columns, rows, encoding, delimiter=",")

# ========== RUTAS DE LANDING PAGE ==========

@app.route("/")
def home():
    return render_template("landing/home.html")

@app.route("/servicios")
def servicios():
    return render_template("landing/servicios.html")

@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        empresa = request.form.get("empresa", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        servicio = request.form.get("servicio", "").strip()
        mensaje = request.form.get("mensaje", "").strip()
        consentimiento = request.form.get("consentimiento") == "on"
        newsletter = request.form.get("newsletter") == "on"

        if not nombre or not email or not mensaje:
            return jsonify({"success": False, "message": "Nombre, correo y mensaje son obligatorios."}), 400
        if len(nombre) > 120 or len(empresa) > 160 or len(telefono) > 40 or len(mensaje) > 5000:
            return jsonify({"success": False, "message": "Uno o más campos superan el límite permitido."}), 400
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            return jsonify({"success": False, "message": "Ingresa un correo electrónico válido."}), 400
        if not consentimiento:
            return jsonify({"success": False, "message": "Debes aceptar la Política de Privacidad."}), 400

        try:
            guardar_mensaje_contacto(nombre, empresa, email, telefono, servicio, mensaje, newsletter)
        except OSError:
            app.logger.exception("No fue posible guardar el mensaje de contacto.")
            return jsonify({"success": False, "message": "No se pudo enviar el mensaje. Inténtalo de nuevo."}), 500
        return jsonify({
            "success": True,
            "message": "¡Gracias por tu mensaje! Nos pondremos en contacto contigo pronto.",
        })

    return render_template("landing/contacto.html")

@app.route("/proyectos")
def proyectos():
    return render_template("landing/proyectos.html")

@app.route("/privacidad")
def privacidad():
    return render_template("landing/privacidad.html")

# ========== RUTAS DEL SISTEMA DE GESTIÓN ==========

@app.route("/sistema/")
def sistema_home():
    return redirect(url_for("sistema_login"))

@app.route("/sistema/login", methods=["GET", "POST"])
def sistema_login():
    if request.method == "POST":
        cliente = request.form.get("cliente", "")
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "")

        admin = USERS.get("admin", {})
        if (
            usuario == "admin"
            and admin.get("active", False)
            and admin.get("password_hash")
            and check_password_hash(admin["password_hash"], clave)
        ):
            session.clear()
            session["admin"] = True
            session["usuario"] = "admin"
            session["rol"] = "admin"
            session["must_change_password"] = admin.get("must_change_password", False)
            session.permanent = True
            log_cambio("SISTEMA", "admin", "Inicio de sesión admin")
            return redirect(url_for("cambiar_clave") if session["must_change_password"] else url_for("admin_panel"))

        if cliente in CLIENTES:
            account = USERS["clients"].get(cliente, {}).get(usuario, {})
            if (
                account.get("active", False)
                and account.get("role") in {"editor", "viewer"}
                and account.get("password_hash")
                and check_password_hash(account["password_hash"], clave)
            ):
                session.clear()
                session["cliente"] = cliente
                session["usuario"] = usuario
                session["rol"] = account["role"]
                session["must_change_password"] = account.get("must_change_password", False)
                session.permanent = True
                log_cambio(cliente, usuario, f"Inicio de sesión ({session['rol']})")
                return redirect(url_for("cambiar_clave") if session["must_change_password"] else url_for("index"))

        return render_template("sistema/login.html", error="Usuario o contraseña incorrectos", clientes=CLIENTES.keys()), 401

    return render_template("sistema/login.html", clientes=CLIENTES.keys())


def is_admin_session():
    return (
        session.get("admin") is True
        and not session.get("must_change_password")
        and USERS.get("admin", {}).get("active", False)
    )


def is_last_active_editor(accounts, username):
    account = accounts[username]
    return (
        account.get("role") == "editor"
        and account.get("active", True)
        and not any(
            name != username and user.get("role") == "editor" and user.get("active", True)
            for name, user in accounts.items()
        )
    )


def active_client_account():
    cliente = session.get("cliente")
    usuario = session.get("usuario")
    if not cliente or cliente not in CLIENTES or not usuario:
        return None
    account = USERS["clients"].get(cliente, {}).get(usuario)
    if (
        not account
        or not account.get("active", False)
        or account.get("must_change_password", False)
        or account.get("role") != session.get("rol")
    ):
        return None
    return account


def get_client_stats(cliente):
    fields, rows, _ = read_csv_file(CLIENTES[cliente]["csv"])
    devices = [row for row in rows if (row.get("#") or "").strip()]
    statuses = {}
    floors = set()
    zones = set()
    loops = set()
    for row in devices:
        status = (row.get("ESTADO") or "").strip() or "Sin estado"
        statuses[status] = statuses.get(status, 0) + 1
        if row.get("PISO"):
            floors.add(row["PISO"].strip())
        if row.get("NOMBRE_UBICACION"):
            zones.add(row["NOMBRE_UBICACION"].strip())
        if row.get("LAZO"):
            loops.add(row["LAZO"].strip())
    _, cameras, _ = read_csv_file(CLIENTES[cliente]["camaras_csv"])
    return {
        "devices": len(devices),
        "cameras": sum(bool((row.get("#") or "").strip()) for row in cameras),
        "statuses": statuses,
        "floors": len(floors),
        "zones": len(zones),
        "loops": len(loops),
    }


@app.route("/sistema/panel")
def index():
    if "usuario" not in session:
        return redirect(url_for("sistema_login"))
    if session.get("admin"):
        return redirect(url_for("admin_panel"))
    if session.get("must_change_password"):
        return redirect(url_for("cambiar_clave"))
    if active_client_account() is None:
        session.clear()
        return redirect(url_for("sistema_login"))
    cliente = session.get("cliente", "")
    if cliente not in CLIENTES:
        session.clear()
        return redirect(url_for("sistema_login"))
    rol = session.get("rol", "viewer")
    stats = get_client_stats(cliente)
    return render_template("sistema/index.html", cliente=cliente, rol=rol, stats=stats)


@app.route("/sistema/cambiar-clave", methods=["GET", "POST"])
def cambiar_clave():
    if "usuario" not in session:
        return redirect(url_for("sistema_login"))
    if request.method == "GET":
        return render_template("sistema/cambiar_clave.html")

    password = request.form.get("nueva_clave", "")
    confirmation = request.form.get("confirmar_clave", "")
    if len(password) < 12:
        return render_template("sistema/cambiar_clave.html", error="La contraseña debe tener al menos 12 caracteres."), 400
    if password != confirmation:
        return render_template("sistema/cambiar_clave.html", error="Las contraseñas no coinciden."), 400

    with file_lock(USERS_FILE):
        users = load_users()
        if session.get("admin"):
            account = users["admin"]
        else:
            account = users["clients"].get(session.get("cliente", ""), {}).get(session["usuario"])
        if account is None:
            session.clear()
            return redirect(url_for("sistema_login"))
        account["password_hash"] = generate_password_hash(password)
        account["must_change_password"] = False
        save_json_atomic(USERS_FILE, users)

    session["must_change_password"] = False
    log_cambio(session.get("cliente", "SISTEMA"), session["usuario"], "Actualización de contraseña")
    return redirect(url_for("admin_panel" if session.get("admin") else "index"))

# Ruta de compatibilidad - redirige al nuevo login
@app.route("/login")
def login_redirect():
    """Ruta de compatibilidad que redirige al login del sistema"""
    return redirect(url_for("sistema_login"))

@app.route("/logout")
def logout():
    if session.get("admin"):
        log_cambio("SISTEMA", "admin", "Cierre de sesión admin")
    elif session.get("cliente"):
        log_cambio(session.get("cliente", ""), session.get("usuario", ""), 
                  f"Cierre de sesión ({session.get('rol', '')})")
    
    session.clear()
    return redirect(url_for("home"))

# ========== RUTAS DE ADMINISTRACIÓN ==========

@app.route("/admin")
def admin_panel():
    if not is_admin_session():
        return redirect(url_for("sistema_login"))
    return render_template("sistema/admin.html", clientes=CLIENTES.keys())

@app.route("/api/admin/clientes")
def api_admin_clientes():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401

    clientes_info = []
    for nombre_cliente, cuentas in USERS["clients"].items():
        for usuario, datos in cuentas.items():
            clientes_info.append({
                "cliente": nombre_cliente,
                "usuario": usuario,
                "rol": datos["role"],
                "activo": datos.get("active", True),
                "requiere_cambio": datos.get("must_change_password", False),
            })
    return jsonify(clientes_info)

@app.route("/api/admin/update_usuario", methods=["POST"])
def api_admin_update_usuario():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    cliente = req.get("cliente")
    usuario = req.get("usuario")
    nuevo_rol = req.get("rol")
    nueva_clave = req.get("clave", "")
    activo = req.get("activo")
    if not isinstance(cliente, str) or not isinstance(usuario, str):
        return jsonify({"error": "Cliente o usuario inválido"}), 400
    if cliente not in CLIENTES or usuario not in USERS["clients"].get(cliente, {}):
        return jsonify({"error": "Usuario no encontrado"}), 404
    if not isinstance(nuevo_rol, str) or nuevo_rol not in {"editor", "viewer"}:
        return jsonify({"error": "Rol inválido"}), 400
    if not isinstance(nueva_clave, str):
        return jsonify({"error": "Contraseña inválida"}), 400
    if nueva_clave and len(nueva_clave) < 12:
        return jsonify({"error": "La contraseña debe tener al menos 12 caracteres"}), 400
    if "activo" in req and not isinstance(activo, bool):
        return jsonify({"error": "Estado inválido"}), 400

    with file_lock(USERS_FILE):
        users = load_users()
        accounts = users["clients"][cliente]
        if is_last_active_editor(accounts, usuario) and (
            nuevo_rol != "editor" or activo is False
        ):
            return jsonify({"error": "No se puede dejar al cliente sin un editor activo"}), 409
        account = users["clients"][cliente][usuario]
        if nueva_clave:
            account["password_hash"] = generate_password_hash(nueva_clave)
            account["must_change_password"] = True
        account["role"] = nuevo_rol
        if isinstance(activo, bool):
            account["active"] = activo
        backup_file(USERS_FILE)
        save_json_atomic(USERS_FILE, users)
    log_cambio("SISTEMA", "admin", f"Actualización usuario {cliente}/{usuario}")
    return jsonify({"success": True})

@app.route("/api/admin/add_usuario", methods=["POST"])
def api_admin_add_usuario():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    cliente = req.get("cliente")
    nuevo_usuario = req.get("usuario", "")
    clave = req.get("clave", "")
    rol = req.get("rol", "viewer")
    if not isinstance(cliente, str):
        return jsonify({"error": "Cliente inválido"}), 400
    if cliente not in CLIENTES:
        return jsonify({"error": "Cliente no encontrado"}), 404
    if not isinstance(nuevo_usuario, str):
        return jsonify({"error": "Usuario inválido"}), 400
    nuevo_usuario = nuevo_usuario.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", nuevo_usuario):
        return jsonify({"error": "El usuario debe tener entre 3 y 40 caracteres válidos"}), 400
    if not isinstance(clave, str) or len(clave) < 12:
        return jsonify({"error": "La contraseña debe tener al menos 12 caracteres"}), 400
    if not isinstance(rol, str) or rol not in {"editor", "viewer"}:
        return jsonify({"error": "Rol inválido"}), 400
    with file_lock(USERS_FILE):
        users = load_users()
        if nuevo_usuario in users["clients"].setdefault(cliente, {}):
            return jsonify({"error": "Usuario ya existe"}), 400
        users["clients"][cliente][nuevo_usuario] = {
            "password_hash": generate_password_hash(clave),
            "role": rol,
            "active": True,
            "must_change_password": True,
        }
        backup_file(USERS_FILE)
        save_json_atomic(USERS_FILE, users)
    log_cambio("SISTEMA", "admin", f"Nuevo usuario creado {cliente}/{nuevo_usuario}")
    return jsonify({"success": True})

@app.route("/api/admin/delete_usuario", methods=["POST"])
def api_admin_delete_usuario():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    cliente = req.get("cliente")
    usuario = req.get("usuario")
    if not isinstance(cliente, str) or not isinstance(usuario, str):
        return jsonify({"error": "Cliente o usuario inválido"}), 400
    if cliente not in CLIENTES or usuario not in USERS["clients"].get(cliente, {}):
        return jsonify({"error": "Usuario no encontrado"}), 404
    with file_lock(USERS_FILE):
        users = load_users()
        accounts = users["clients"][cliente]
        if accounts[usuario].get("role") == "editor" and accounts[usuario].get("active", True):
            active_editors = sum(
                account.get("role") == "editor" and account.get("active", True)
                for name, account in accounts.items()
                if name != usuario
            )
            if active_editors == 0:
                return jsonify({"error": "No se puede eliminar el último editor activo del cliente"}), 409
        del accounts[usuario]
        backup_file(USERS_FILE)
        save_json_atomic(USERS_FILE, users)
    log_cambio("SISTEMA", "admin", f"Usuario eliminado {cliente}/{usuario}")
    return jsonify({"success": True})


@app.route("/api/admin/clientes", methods=["POST"])
def api_admin_cliente_estado():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    cliente = req.get("cliente")
    usuario = req.get("usuario")
    activo = req.get("activo")
    if not isinstance(cliente, str) or not isinstance(usuario, str):
        return jsonify({"error": "Cliente o usuario inválido"}), 400
    if cliente not in CLIENTES or usuario not in USERS["clients"].get(cliente, {}):
        return jsonify({"error": "Usuario no encontrado"}), 404
    if not isinstance(activo, bool):
        return jsonify({"error": "Estado inválido"}), 400
    with file_lock(USERS_FILE):
        users = load_users()
        accounts = users["clients"][cliente]
        if not activo and is_last_active_editor(accounts, usuario):
            return jsonify({"error": "No se puede dejar al cliente sin un editor activo"}), 409
        users["clients"][cliente][usuario]["active"] = activo
        backup_file(USERS_FILE)
        save_json_atomic(USERS_FILE, users)
    log_cambio("SISTEMA", "admin", f"Cuenta {cliente}/{usuario} {'activada' if activo else 'desactivada'}")
    return jsonify({"success": True})

@app.route("/api/admin/logs")
def api_admin_logs():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    if not LOG_FILE.exists():
        return jsonify([])
    with LOG_FILE.open(encoding="utf-8") as file:
        logs = json.load(file)
    return jsonify(logs[-50:][::-1])

@app.route("/api/admin/contactos")
def api_admin_contactos():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    if not CONTACTS_FILE.exists():
        return jsonify([])
    _, contacts, _ = read_csv_file(CONTACTS_FILE, delimiter=",")
    return jsonify(list(reversed(contacts)))

@app.route("/api/admin/contacto_estado", methods=["POST"])
def api_admin_contacto_estado():
    if not is_admin_session():
        return jsonify({"error": "No autorizado"}), 401
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    email = req.get("email")
    fecha = req.get("fecha")
    hora = req.get("hora")
    nuevo_estado = req.get("estado")
    if nuevo_estado not in {"Leído", "Respondido"}:
        return jsonify({"error": "Estado inválido"}), 400
    if not CONTACTS_FILE.exists():
        return jsonify({"error": "Archivo no encontrado"}), 404

    with file_lock(CONTACTS_FILE):
        fieldnames, contacts, encoding = read_csv_file(CONTACTS_FILE, delimiter=",")
        matched = False
        for contact in contacts:
            if contact.get("Email") == email and contact.get("Fecha") == fecha and contact.get("Hora") == hora:
                contact["Estado"] = nuevo_estado
                matched = True
        if not matched:
            return jsonify({"error": "Mensaje no encontrado"}), 404
        write_csv_atomic(CONTACTS_FILE, fieldnames, contacts, encoding, delimiter=",")
    log_cambio("SISTEMA", "admin", f"Estado de mensaje actualizado a {nuevo_estado}")
    return jsonify({"success": True})

# ========== RUTAS EXISTENTES ==========

@app.route("/api/data")
def api_data():
    if active_client_account() is None:
        return jsonify({"error": "No autorizado"}), 401
    csv_path = CLIENTES[session["cliente"]]["csv"]
    try:
        _, rows, _ = read_csv_file(csv_path)
    except OSError:
        app.logger.exception("No fue posible leer los dispositivos del cliente.")
        return jsonify({"error": "No fue posible leer los datos del cliente"}), 500
    data = [{
        "SERIAL": (row.get("#") or "").strip(),
        "TIPO": (row.get("TIPO") or "").strip(),
        "PISO": (row.get("PISO") or "").strip(),
        "NOMBRE_UBICACION": (row.get("NOMBRE_UBICACION") or "").strip(),
        "LAZO": (row.get("LAZO") or "").strip(),
        "DIRECCION": (row.get("DIRECCION") or "").strip(),
        "FECHA_MANTO": (row.get("FECHA_MANTO") or "").strip(),
        "ESTADO": (row.get("ESTADO") or "").strip(),
        "OBSERVACION": (row.get("OBSERVACION") or "").strip(),
    } for row in rows if (row.get("#") or "").strip()]
    response = jsonify(data)
    response.headers["X-Data-Revision"] = current_revision(csv_path)
    response.headers["Cache-Control"] = "no-store"
    return response

@app.route("/api/update", methods=["POST"])
def api_update():
    account = active_client_account()
    if account is None:
        return jsonify({"error": "No autorizado"}), 401
    if account["role"] != "editor":
        return jsonify({"error": "Sin permisos de edición"}), 403
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    allowed_fields = {
        "TIPO": 120,
        "PISO": 80,
        "NOMBRE_UBICACION": 200,
        "LAZO": 80,
        "DIRECCION": 120,
        "FECHA_MANTO": 20,
        "ESTADO": 80,
        "OBSERVACION": 2000,
    }
    csv_path = CLIENTES[session["cliente"]]["csv"]
    revision, error, status = update_csv_record(
        csv_path, req.get("SERIAL"), req.get("campo"), req.get("valor"),
        allowed_fields, req.get("revision"), update_date=True,
    )
    if error:
        return jsonify({"error": error}), status
    log_cambio(session["cliente"], session["usuario"], f"Edición campo {req['campo']}", f"ID {req['SERIAL']}")
    return jsonify({"success": True, "revision": revision})


@app.route("/api/add", methods=["POST"])
def api_add():
    account = active_client_account()
    if account is None:
        return jsonify({"error": "No autorizado"}), 401
    if account["role"] != "editor":
        return jsonify({"error": "Sin permisos de edición"}), 403
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    values = req.get("device")
    if not isinstance(values, dict):
        return jsonify({"error": "Datos del dispositivo inválidos"}), 400
    serial = values.get("SERIAL", "")
    if not isinstance(serial, str):
        return jsonify({"error": "El identificador debe ser texto"}), 400
    serial = serial.strip()
    if not serial or len(serial) > 120:
        return jsonify({"error": "El identificador es obligatorio (máximo 120 caracteres)"}), 400
    csv_path = CLIENTES[session["cliente"]]["csv"]
    revision = req.get("revision")
    with file_lock(csv_path):
        if not revision or current_revision(csv_path) != revision:
            return jsonify({"error": "Los datos cambiaron. Recarga antes de agregar."}), 409
        matrix = None
        encoding = "utf-8"
        for candidate in csv_encodings(csv_path):
            try:
                with csv_path.open(encoding=candidate, newline="") as file:
                    matrix = list(csv.reader(file, delimiter=";"))
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
        if matrix is None:
            return jsonify({"error": "No fue posible leer el archivo de datos"}), 500
        if not matrix or "#" not in matrix[0]:
            return jsonify({"error": "El archivo CSV no tiene el esquema esperado"}), 500
        headers = matrix[0]
        serial_index = headers.index("#")
        if any(serial_index < len(row) and row[serial_index].strip() == serial for row in matrix[1:]):
            return jsonify({"error": "Ya existe un dispositivo con ese identificador"}), 409
        editable_fields = {
            "TIPO": 120, "PISO": 80, "NOMBRE_UBICACION": 200, "LAZO": 80,
            "DIRECCION": 120, "ESTADO": 80, "OBSERVACION": 2000,
        }
        row = [""] * max(max(map(len, matrix), default=len(headers)), len(headers))
        row[serial_index] = serial
        for field, max_length in editable_fields.items():
            value = values.get(field, "")
            if not isinstance(value, str) or len(value) > max_length:
                return jsonify({"error": f"Valor inválido para {field}"}), 400
            if field in headers:
                row[headers.index(field)] = value.strip()
        if "FECHA_MANTO" in headers:
            row[headers.index("FECHA_MANTO")] = datetime.now().strftime("%d/%m/%Y")
        if "ESTADO" in headers and not row[headers.index("ESTADO")]:
            row[headers.index("ESTADO")] = "Pendiente"
        matrix.append(row)
        write_csv_matrix_atomic(csv_path, matrix, encoding)
    log_cambio(session["cliente"], session["usuario"], "Alta de dispositivo", f"ID {serial}")
    return jsonify({"success": True, "revision": current_revision(csv_path)}), 201

@app.route("/api/camaras")
def api_camaras():
    if active_client_account() is None:
        return jsonify({"error": "No autorizado"}), 401
    camaras_csv = CLIENTES[session["cliente"]]["camaras_csv"]
    try:
        _, rows, _ = read_csv_file(camaras_csv)
    except OSError:
        app.logger.exception("No fue posible leer las cámaras del cliente.")
        return jsonify({"error": "No fue posible leer los datos de cámaras"}), 500
    data = [{
        "SERIAL": (row.get("#") or "").strip(),
        "UBICACION": (row.get("UBICACION") or "").strip(),
        "TIPO": (row.get("TIPO") or "").strip(),
        "ESTADO": (row.get("ESTADO") or "").strip(),
        "DIAGRAMA": (row.get("DIAGRAMA") or "").strip(),
        "OBSERVACION": (row.get("OBSERVACION") or "").strip(),
    } for row in rows if (row.get("#") or "").strip()]
    response = jsonify(data)
    response.headers["X-Data-Revision"] = current_revision(camaras_csv)
    response.headers["Cache-Control"] = "no-store"
    return response

@app.route("/api/update_camaras", methods=["POST"])
def api_update_camaras():
    account = active_client_account()
    if account is None:
        return jsonify({"error": "No autorizado"}), 401
    if account["role"] != "editor":
        return jsonify({"error": "Sin permisos de edición"}), 403
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        return jsonify({"error": "Solicitud inválida"}), 400
    allowed_fields = {"UBICACION": 200, "TIPO": 120, "ESTADO": 80, "OBSERVACION": 2000}
    camaras_csv = CLIENTES[session["cliente"]]["camaras_csv"]
    revision, error, status = update_csv_record(
        camaras_csv, req.get("SERIAL"), req.get("campo"), req.get("valor"),
        allowed_fields, req.get("revision"),
    )
    if error:
        return jsonify({"error": error}), status
    log_cambio(session["cliente"], session["usuario"], f"Edición de cámara {req['campo']}", f"ID {req['SERIAL']}")
    return jsonify({"success": True, "revision": revision})

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "").lower() == "true",
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
    )