"""Integração HTTP com SQLite temporário; não altera banco.db."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from database import connect
from main import create_app


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.client = TestClient(create_app(self.db_path))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def payload(self):
        return {"name": "Serviço de teste", "category": "Serviços", "phone": "(00) 00000-0000",
                "address": "Endereço de teste", "hours": "", "description": "Descrição de teste",
                "consent": True, "whatsapp": False, "request_id": str(uuid4())}

    def test_assets_and_private_files(self):
        self.assertIn('/static/script.js', self.client.get("/").text)
        for path in ("/static/style.css", "/static/script.js", "/api/categorias"):
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ("/banco.db", "/main.py", "/api/sugestoes"):
            self.assertIn(self.client.get(path).status_code, (404, 405))
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)

    def test_catalog_and_pending_visibility(self):
        rows = self.client.get("/api/estabelecimentos").json()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["is_demo"] and row["phone"] is None for row in rows))
        self.assertNotIn("request_id", rows[0])
        result = self.client.post("/api/sugestoes", json=self.payload())
        self.assertEqual(result.status_code, 201)
        protocol = result.json()["protocol"]
        with connect(self.db_path) as db:
            row = db.execute("SELECT * FROM establishments WHERE id = ?", (protocol,)).fetchone()
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["phone"], "00000000000")
            self.assertEqual(row["is_demo"], 0)
        self.assertEqual(self.client.get(f"/api/estabelecimentos/{protocol}").status_code, 404)
        self.assertEqual(len(self.client.get("/api/estabelecimentos").json()), 6)

    def test_invalid_and_privileged_fields(self):
        for changes in ({"name": "   "}, {"description": "x"}, {"phone": "abc12345678"},
                        {"phone": "123"}, {"category": "Inexistente"}, {"consent": False},
                        {"consent": "true"}, {"status": "approved"}, {"is_demo": True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post("/api/sugestoes", json={**self.payload(), **changes}).status_code, 422)

    def test_idempotency_and_restart(self):
        payload = self.payload()
        first = self.client.post("/api/sugestoes", json=payload)
        second = self.client.post("/api/sugestoes", json=payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["protocol"], second.json()["protocol"])
        self.assertEqual(self.client.post("/api/sugestoes", json={**payload, "name": "Outro nome"}).status_code, 409)
        with TestClient(create_app(self.db_path)) as restarted:
            self.assertEqual(len(restarted.get("/api/estabelecimentos").json()), 6)
            with connect(self.db_path) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM establishments WHERE status = 'pending'").fetchone()[0], 1)

    def test_empty_database(self):
        with TestClient(create_app(Path(self.temp.name) / "empty.db", seed_demo=False)) as client:
            self.assertEqual(client.get("/api/estabelecimentos").json(), [])


if __name__ == "__main__":
    unittest.main()
