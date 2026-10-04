import pytest

from patient_document_ocr.scan_intake import PdfOcrClient, RetryPolicy, ScanIntake, process_scan


class CompletedOcr:
    async def ocr(self, pdf_base64: str, language: str, request_id: str):
        assert (pdf_base64, language, request_id) == ("cGRm", "eng", "appt-42")
        return {"text": "Diagnosis: private clinical detail"}

    async def get_job(self, job_id: str):
        raise AssertionError("completed OCR should not be polled")


@pytest.mark.asyncio
async def test_notification_excludes_ocr_text_but_result_keeps_it():
    intake = ScanIntake(
        appointment_id="appt-42",
        patient_id="patient-7",
        pdf_base64="cGRm",
    )

    result = await process_scan(CompletedOcr(), intake)

    assert result.searchable_text == "Diagnosis: private clinical detail"
    assert result.notification == (
        "Document processing is complete for appointment appt-42. "
        "Your care team can now review it."
    )
    assert "Diagnosis" not in result.notification
    assert result.patient_id not in result.notification


@pytest.mark.asyncio
async def test_ocr_request_uses_exact_body_and_idempotency_header(monkeypatch):
    import httpx

    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "data": {"text": "indexed"}, "error": None, "metadata": {}})

    client = PdfOcrClient(
        "test-key",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1, base_delay_seconds=0),
    )
    try:
        data = await client.ocr("cGRm", "eng", "appt-42")
    finally:
        await client.close()

    assert data == {"text": "indexed"}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/pdf/ocr"
    assert seen[0].headers["Idempotency-Key"] == "appt-42"
    assert seen[0].read() == b'{"pdf":"cGRm","lang":"eng"}'


@pytest.mark.asyncio
async def test_process_scan_polls_until_text_is_ready(monkeypatch):
    async def no_delay(_seconds):
        pass

    monkeypatch.setattr("patient_document_ocr.scan_intake.asyncio.sleep", no_delay)

    class PendingOcr:
        calls = 0

        async def ocr(self, *_args):
            return {"job_id": "job-1"}

        async def get_job(self, job_id):
            assert job_id == "job-1"
            self.calls += 1
            return {"status": "processing"} if self.calls < 3 else {"status": "completed", "text": "indexed"}

    client = PendingOcr()
    result = await process_scan(client, ScanIntake(appointment_id="appt-42", patient_id="patient-7", pdf_base64="cGRm"))
    assert result.searchable_text == "indexed"
    assert client.calls == 3
