import csv
import json
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook

from rca_agent.ingestion import ingest


ROOT = Path(__file__).resolve().parents[1]


def test_ingests_csv_json_and_xlsx():
    tmp_path = ROOT / "reports" / "test-artifacts" / uuid4().hex
    tmp_path.mkdir(parents=True)
    records = [{"id": "BUG-1", "title": "Falha"}, {"id": "BUG-2", "title": "Erro"}]

    csv_path = tmp_path / "bugs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "title"])
        writer.writeheader()
        writer.writerows(records)

    json_path = tmp_path / "bugs.json"
    json_path.write_text(json.dumps({"bugs": records}), encoding="utf-8")

    xlsx_path = tmp_path / "bugs.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "title"])
    sheet.append(["BUG-1", "Falha"])
    sheet.append(["BUG-2", "Erro"])
    workbook.save(xlsx_path)

    assert len(ingest(csv_path)) == 2
    assert len(ingest(json_path)) == 2
    assert len(ingest(xlsx_path)) == 2
