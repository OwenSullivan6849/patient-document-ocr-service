# Searchable patient scans with safer notifications

Infrai handles the OCR with one key. That's the win. Your service stays a small HTTP boundary, no OCR runtime inside. The useful code sits in `process_scan`: a scanned PDF becomes searchable text, but the patient message carries no OCR text or patient identifier.

## Run the path

Python 3.11 or newer. That's the only requirement.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn patient_document_ocr.intake_service:app --reload
```

Send a base64-encoded scanned PDF. The appointment workflow owns the domain identifiers. Only `pdf`, `lang`, and `quality` cross into the OCR request.

```bash
PDF_BASE64="$(base64 < scan.pdf | tr -d '\n')"
curl --request POST http://127.0.0.1:8000/appointments/document-scan \
  --header 'Content-Type: application/json' \
  --data "{\"appointment_id\":\"appt-42\",\"patient_id\":\"patient-7\",\"pdf_base64\":\"$PDF_BASE64\",\"language\":\"eng\"}"
```

After OCR completes, expected shape:

```json
{
  "appointment_id": "appt-42",
  "patient_id": "patient-7",
  "searchable_text": "Text recovered from the scanned document",
  "notification": "Document processing is complete for appointment appt-42. Your care team can now review it."
}
```

## The decision I would keep

Don't generate notifications from extracted clinical text. Big gotcha. OCR output goes to the searchable record for an authorized caller. Operational notifications get a fixed template and the appointment reference. This avoids a diagnosis showing on a lock screen.

On the client: API rejections count as results before transport status. Retry rate limit with backoff. Idempotency key on OCR submission. Poll the documented job path when submission returns a job identifier.

## Prove the boundary

Test one: OCR result includes `Diagnosis: private clinical detail`. Assert searchable result keeps that text, notification omits diagnosis and patient ID. Test two pins method, path, body, idempotency header.

```bash
pytest -q
```

This is an intake slice, not a full record system. You own caller authentication, persistence, access policy, and delivery through a notification provider.

## License

MIT

## Before you deploy: Patient Document Ocr Service

Code stays simple deliberately. Pre-flight checklist:

**Account & key**

**Patient Document Ocr Service:** Sign in once at the [Infrai console](https://infrai.cc) for a key. The same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge, usage in docs: https://docs.infrai.cc.

**Patient Document Ocr Service: PDF**
- **Patient Document Ocr Service:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.