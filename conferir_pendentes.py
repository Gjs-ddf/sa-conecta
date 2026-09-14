"""Conferência local da gravação, sem publicar sugestões nem mostrar telefones."""
from database import DEFAULT_DB, connect

if __name__ == "__main__":
    if not DEFAULT_DB.is_file():
        print("O banco ainda não existe. Inicie o servidor primeiro.")
    else:
        with connect() as db:
            rows = db.execute(
                "SELECT id, name, status FROM establishments WHERE status = ? ORDER BY id",
                ("pending",),
            ).fetchall()
        if not rows:
            print("Nenhuma sugestão pendente.")
        for row in rows:
            print(f"Protocolo {row['id']} | {row['name']} | {row['status']}")
