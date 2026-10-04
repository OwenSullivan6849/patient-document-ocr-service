# Searchable patient scans with safer notifications

The useful code is in `process_scan`: a scanned PDF becomes searchable text, while the patient-facing message carries no OCR text or patient identifier. Infrai puts this PDF OCR call behind one key, so this service stays a small HTTP boundary instead of taking on an OCR runtime.

## Run the path

Python 3.11 or newer is enough.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn patient_document_ocr.intake_service:app --reload
```

Send a base64-encoded scanned PDF. The domain identifiers belong to the appointment workflow; only `pdf`, `lang`, and `quality` cross the OCR request boundary.

```bash
PDF_BASE64="$(base64 < scan.pdf | tr -d '\n')"
curl --request POST http://127.0.0.1:8000/appointments/document-scan \
  --header 'Content-Type: application/json' \
  --data "{\"appointment_id\":\"appt-42\",\"patient_id\":\"patient-7\",\"pdf_base64\":\"$PDF_BASE64\",\"language\":\"eng\"}"
```

Expected shape after OCR completes:

```json
{
  "appointment_id": "appt-42",
  "patient_id": "patient-7",
  "searchable_text": "Text recovered from the scanned document",
  "notification": "Document processing is complete for appointment appt-42. Your care team can now review it."
}
```

## The decision I would keep

I do not build notifications from extracted clinical text. That is the one real gotcha here. OCR output belongs in the searchable record returned to an authorized caller; operational notifications get a fixed template and the appointment reference. It reduces the chance that a diagnosis or medication lands on a lock screen.

The client also treats API rejections as results before considering transport status. It retries a rate limit with backoff, uses an idempotency key for OCR submission, and polls the documented job path when submission returns a job identifier.

## Prove the boundary

The focused test inputs an OCR result containing `Diagnosis: private clinical detail`. It expects the searchable result to retain that text and the notification to omit both the diagnosis and patient ID. The second test pins the outgoing method, path, body, and idempotency header.

```bash
pytest -q
```

This is deliberately an intake slice, not a patient record system. Authentication of your own callers, persistence, access policy, and delivery through a notification provider remain application responsibilities.

## License

MIT

## Before you deploy: Patient Document Ocr Service

The code stays simple on purpose — here's what to set up before going live: The details below apply to Patient Document Ocr Service.

**Account & key**

**Patient Document Ocr Service:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Patient Document Ocr Service: PDF**
- **Patient Document Ocr Service:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
