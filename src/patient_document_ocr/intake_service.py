from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .scan_intake import InfraiError, InfraiTransportError, PdfOcrClient, ScanIntake, IntakeResult, process_scan


app = FastAPI(title="Patient document OCR intake")


@app.post("/appointments/document-scan", response_model=IntakeResult)
async def submit_document(intake: ScanIntake) -> IntakeResult:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is not configured")
    client = PdfOcrClient(api_key)
    try:
        return await process_scan(client, intake)
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.detail.get("message")}) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()
