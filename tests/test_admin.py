"""Regressões de autenticação, autorização e fluxo de moderação em banco temporário."""
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from database import connect, init_database, save_suggestion
from main import create_app
from security import COOKIE_NAME, init_security, set_admin

PASSWORD = "Apenas-para-teste-12345"


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.client = TestClient(create_app(self.path))
        self.client.__enter__()
        set_admin("gabriel", PASSWORD, self.path)
        self.payload = {"name": "Serviço de teste", "category": "Serviços", "phone": "00000000000",
                        "address": "Endereço de teste", "hours": "", "description": "Descrição de teste",
                        "whatsapp": False, "consent": True, "request_id": str(uuid4())}
        self.item = self.client.post("/api/sugestoes", json=self.payload).json()["protocol"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def enter(self):
        response = self.client.post("/api/admin/login", json={"username": "gabriel", "password": PASSWORD}, headers={"X-Requested-With": "SaConecta"})
        self.assertEqual(response.status_code, 200)
        csrf = self.client.get("/api/admin/session").json()["csrf"]
        self.headers = {"X-CSRF-Token": csrf, "Origin": "http://testserver"}
        return response

    def test_all_admin_operations_require_session(self):
        self.assertEqual(self.client.get("/admin", follow_redirects=False).headers["location"], "/admin/login")
        self.assertEqual(self.client.get("/api/admin/contatos").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/session").status_code, 401)
        for method, url, body in [("PATCH", f"/api/admin/contatos/{self.item}/status", {"revision": 1, "status": "approved"}),
                                  ("DELETE", f"/api/admin/contatos/{self.item}", {"revision": 1}),
                                  ("PUT", f"/api/admin/contatos/{self.item}", {})]:
            self.assertEqual(self.client.request(method, url, json=body).status_code, 401)

    def test_login_cookie_csrf_and_logout_revocation(self):
        response = self.enter()
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertEqual(self.client.get("/admin").headers["cache-control"], "no-store")
        path = f"/api/admin/contatos/{self.item}/status"
        body = {"revision": 1, "status": "approved"}
        self.assertEqual(self.client.patch(path, json=body).status_code, 403)
        self.assertEqual(self.client.patch(path, json=body, headers={**self.headers, "Origin": "https://example.org"}).status_code, 403)
        token = self.client.cookies.get(COOKIE_NAME)
        self.assertEqual(self.client.post("/api/admin/logout", headers=self.headers).status_code, 200)
        self.client.cookies.set(COOKIE_NAME, token)
        self.assertEqual(self.client.get("/api/admin/contatos").status_code, 401)

    def test_complete_moderation_and_revision_conflict(self):
        self.enter()
        edit = {key: self.payload[key] for key in ["name", "category", "phone", "address", "hours", "description", "whatsapp"]}
        edit.update(name="Nome revisado", revision=1)
        base = f"/api/admin/contatos/{self.item}"
        self.assertEqual(self.client.put(base, json=edit, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.put(base, json=edit, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.get(f"/api/estabelecimentos/{self.item}").status_code, 404)
        self.assertEqual(self.client.patch(base+"/status", json={"revision": 2, "status": "approved"}, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/estabelecimentos/{self.item}").json()["name"], "Nome revisado")
        self.assertEqual(self.client.patch(base+"/status", json={"revision": 3, "status": "rejected"}, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/estabelecimentos/{self.item}").status_code, 404)
        self.assertEqual(self.client.request("DELETE", base, json={"revision": 4}, headers=self.headers).status_code, 200)
        self.assertNotIn(self.item, [item["id"] for item in self.client.get("/api/admin/contatos").json()])
        new = self.client.post("/api/sugestoes", json={**self.payload, "request_id": str(uuid4())}).json()["protocol"]
        self.assertGreater(new, self.item)
        self.assertEqual(self.client.request("DELETE", base, json={"revision": 1}, headers=self.headers).status_code, 404)

    def test_invalid_credentials_rate_limit_and_login_csrf(self):
        body = {"username": "gabriel", "password": "incorreta"}
        self.assertEqual(self.client.post("/api/admin/login", json=body).status_code, 403)
        headers = {"X-Requested-With": "SaConecta"}
        for _ in range(5):
            self.assertEqual(self.client.post("/api/admin/login", json=body, headers=headers).status_code, 401)
        self.assertEqual(self.client.post("/api/admin/login", json=body, headers=headers).status_code, 429)

    def test_expired_session_and_password_reset(self):
        self.enter()
        with connect(self.path) as db:
            db.execute("UPDATE admin_sessions SET expires_at = ?", (int(time.time()) - 1,))
        self.assertEqual(self.client.get("/api/admin/contatos").status_code, 401)
        self.enter()
        set_admin("gabriel", "Nova-senha-de-teste-456", self.path, replace=True)
        self.assertEqual(self.client.get("/api/admin/contatos").status_code, 401)
        with connect(self.path) as db:
            account = dict(db.execute("SELECT * FROM admin_account").fetchone())
            self.assertNotIn(PASSWORD, str(account))
            self.assertNotIn("Nova-senha-de-teste-456", str(account))

    def test_existing_data_and_seed_remain_stable(self):
        init_database(self.path)
        init_security(self.path)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT status FROM establishments WHERE id=?", (self.item,)).fetchone()[0], "pending")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM establishments").fetchone()[0], 7)
        self.enter()
        self.assertNotIn("request_id", self.client.get("/api/admin/contatos").json()[0])
        self.assertEqual(self.client.get("/static/admin.js").status_code, 200)
        self.assertEqual(self.client.get("/static/admin.css").status_code, 200)

    def test_upgrade_from_database_without_admin_preserves_pending(self):
        legacy = Path(self.temp.name) / "legacy.db"
        init_database(legacy)
        saved = save_suggestion(self.payload, legacy)
        with connect(legacy) as db:
            before = dict(db.execute("SELECT * FROM establishments WHERE id=?", (saved,)).fetchone())
            self.assertNotIn("revision", before)
        with TestClient(create_app(legacy)) as upgraded:
            self.assertEqual(upgraded.get(f"/api/estabelecimentos/{saved}").status_code, 404)
            with connect(legacy) as db:
                after = dict(db.execute("SELECT * FROM establishments WHERE id=?", (saved,)).fetchone())
                self.assertEqual(after.pop("revision"), 1)
                self.assertEqual(before, after)

    def test_invalid_admin_edit_and_demo_mark_preserved(self):
        self.enter()
        edit = {key: self.payload[key] for key in ["name", "category", "phone", "address", "hours", "description", "whatsapp"]}
        for change in ({"phone": ""}, {"name": " "}, {"category": "Inválida"}, {"is_demo": False}, {"status": "approved"}):
            self.assertEqual(self.client.put(f"/api/admin/contatos/{self.item}", json={**edit, "revision": 1, **change}, headers=self.headers).status_code, 422)
        demo = next(row for row in self.client.get("/api/admin/contatos").json() if row["is_demo"])
        data = {key: demo[key] for key in ["name", "category", "address", "hours", "description", "revision"]}
        data.update(phone="", whatsapp=False)
        self.assertEqual(self.client.put(f'/api/admin/contatos/{demo["id"]}', json=data, headers=self.headers).status_code, 200)
        self.assertTrue(self.client.get(f'/api/estabelecimentos/{demo["id"]}').json()["is_demo"])


if __name__ == "__main__":
    unittest.main()
