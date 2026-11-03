import csv
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import app as app_module
from werkzeug.security import generate_password_hash


DEVICE_HEADER = "#;TIPO;PISO;NOMBRE_UBICACION;LAZO;DIRECCION;FECHA_MANTO;ESTADO;OBSERVACION\n"
CAMERA_HEADER = "#;UBICACION;TIPO;ESTADO;DIAGRAMA;OBSERVACION\n"


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.instance = self.root / "instance"
        self.instance.mkdir()
        self.device_path = self.root / "devices.csv"
        self.camera_path = self.root / "cameras.csv"
        self.device_path.write_text(
            DEVICE_HEADER + "D-1;Sensor;1;Entrada;L1;01;01/01/2025;OK;Original\n",
            encoding="utf-8",
        )
        self.camera_path.write_text(
            CAMERA_HEADER + "C-1;Entrada;IP;OK;diagrama_entrada.svg;Activa\n",
            encoding="utf-8",
        )
        self.users_path = self.instance / "users.json"
        self.users_path.write_text(json.dumps({
            "admin": {
                "password_hash": generate_password_hash("admin test password 123"),
                "active": True,
                "must_change_password": False,
            },
            "clients": {
                "acme": {
                    "editor": {
                        "password_hash": generate_password_hash("editor test password 123"),
                        "role": "editor",
                        "active": True,
                        "must_change_password": False,
                    },
                    "viewer": {
                        "password_hash": generate_password_hash("viewer test password 123"),
                        "role": "viewer",
                        "active": True,
                        "must_change_password": False,
                    },
                }
            },
        }), encoding="utf-8")
        self.patches = [
            patch.object(app_module, "USERS_FILE", self.users_path),
            patch.object(app_module, "BACKUP_DIR", self.instance / "backups"),
            patch.object(app_module, "LOG_FILE", self.root / "activity.json"),
            patch.object(app_module, "CONTACTS_FILE", self.root / "contacts.csv"),
            patch.object(app_module, "CLIENTES", {
                "acme": {"csv": self.device_path, "camaras_csv": self.camera_path}
            }),
        ]
        for item in self.patches:
            item.start()
        app_module.USERS = app_module.load_users()
        self.previous_testing = app_module.app.config.get("TESTING", False)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.csrf = self.client.get("/sistema/login").get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^"]+)"', self.csrf)
        self.token = match.group(1)

    def tearDown(self):
        app_module.app.config["TESTING"] = self.previous_testing
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def set_session(self, **values):
        with self.client.session_transaction() as session:
            session["_csrf_token"] = self.token
            session.update(values)

    def editor_session(self):
        self.set_session(cliente="acme", usuario="editor", rol="editor", must_change_password=False)

    def admin_session(self):
        self.set_session(admin=True, usuario="admin", rol="admin", must_change_password=False)

    def post_json(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.token})

    def test_public_pages_render(self):
        for path in ("/", "/servicios", "/proyectos", "/contacto", "/privacidad", "/sistema/login"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_static_svg_images_are_valid_xml(self):
        image_dir = Path(app_module.app.root_path) / "static" / "img"
        for image in image_dir.rglob("*.svg"):
            with self.subTest(image=image.name):
                ElementTree.parse(image)

    def test_initial_password_must_be_rotated_before_access(self):
        users = app_module.load_users()
        users["clients"]["acme"]["editor"]["must_change_password"] = True
        self.users_path.write_text(json.dumps(users), encoding="utf-8")
        login = self.client.post("/sistema/login", data={
            "cliente": "acme",
            "usuario": "editor",
            "clave": "editor test password 123",
            "csrf_token": self.token,
        })
        self.assertEqual(login.status_code, 302)
        self.assertIn("/sistema/cambiar-clave", login.headers["Location"])

        change_page = self.client.get("/sistema/cambiar-clave")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            change_page.get_data(as_text=True),
        ).group(1)
        changed = self.client.post("/sistema/cambiar-clave", data={
            "nueva_clave": "new secure test password 456",
            "confirmar_clave": "new secure test password 456",
            "csrf_token": token,
        })
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(self.client.get("/sistema/panel").status_code, 200)
        self.assertFalse(app_module.load_users()["clients"]["acme"]["editor"]["must_change_password"])

    def test_admin_dashboard_renders_for_admin(self):
        self.admin_session()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Usuarios y permisos", response.get_data(as_text=True))

    def test_mutations_require_csrf(self):
        self.editor_session()
        response = self.client.post("/api/update", json={})
        self.assertEqual(response.status_code, 400)

    def test_editor_update_is_backed_up_and_rejects_stale_revision(self):
        self.editor_session()
        response = self.client.get("/api/data")
        revision = response.headers["X-Data-Revision"]
        update = self.post_json("/api/update", {
            "SERIAL": "D-1", "campo": "ESTADO", "valor": "Falla", "revision": revision,
        })
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["success"], True)
        self.assertTrue(list((self.instance / "backups").glob("devices-*.csv")))
        self.assertIn(";Falla;", self.device_path.read_text(encoding="utf-8"))

        stale = self.post_json("/api/update", {
            "SERIAL": "D-1", "campo": "ESTADO", "valor": "OK", "revision": revision,
        })
        self.assertEqual(stale.status_code, 409)

    def test_update_rejects_unapproved_csv_fields(self):
        self.editor_session()
        revision = self.client.get("/api/data").headers["X-Data-Revision"]
        response = self.post_json("/api/update", {
            "SERIAL": "D-1", "campo": "#", "valor": "D-2", "revision": revision,
        })
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_edit(self):
        self.set_session(cliente="acme", usuario="viewer", rol="viewer", must_change_password=False)
        revision = self.client.get("/api/data").headers["X-Data-Revision"]
        response = self.post_json("/api/update", {
            "SERIAL": "D-1", "campo": "ESTADO", "valor": "Falla", "revision": revision,
        })
        self.assertEqual(response.status_code, 403)

    def test_admin_user_listing_never_returns_password_hashes(self):
        self.admin_session()
        response = self.client.get("/api/admin/clientes")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password_hash", response.get_data(as_text=True))
        self.assertNotIn("admin test password 123", response.get_data(as_text=True))

    def test_device_can_be_added_without_overwriting_existing_record(self):
        self.editor_session()
        revision = self.client.get("/api/data").headers["X-Data-Revision"]
        response = self.post_json("/api/add", {
            "revision": revision,
            "device": {
                "SERIAL": "D-2", "TIPO": "Detector", "PISO": "2",
                "NOMBRE_UBICACION": "Pasillo", "LAZO": "L2",
                "DIRECCION": "02", "ESTADO": "Pendiente", "OBSERVACION": "",
            },
        })
        self.assertEqual(response.status_code, 201)
        with self.device_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file, delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["#"], "D-2")


if __name__ == "__main__":
    unittest.main()
