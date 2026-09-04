import base64
from io import BytesIO
import zipfile

import app


def test_full_excel_export_contract_present():
    source = open(app.__file__, encoding="utf-8").read()
    for token in ("full-excel-button", "full-excel-download", "Download full results Excel", "download_full_results_excel"):
        assert token in source


def test_full_excel_export_is_valid_xlsx():
    result = app.download_full_results_excel(
        1, None, "2026-06-01", "mixed", 100, 50, 25, 2, 50, 90, 90, 90,
        [], None, None, None, None, None, None,
    )
    assert result["filename"].endswith(".xlsx")
    raw = base64.b64decode(result["content"])
    assert raw[:4] == b"PK\x03\x04"
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        assert "Read Me" in workbook_xml
        assert "Live Forecast" in workbook_xml
        assert "Design Evidence" in workbook_xml
