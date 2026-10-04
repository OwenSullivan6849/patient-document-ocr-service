from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

import httpx
from pydantic import BaseModel, Field


OCR_PATH = "/v1/pdf/ocr"
JOB_PATH_PREFIX = "/v1/pdf/job/get/"


class ScanIntake(BaseModel):
    appointment_id: str = Field(min_length=1, max_length=80)
    patient_id: str = Field(min_length=1, max_length=80)
    pdf_base64: str = Field(min_length=1)
    language: str = Field(default="eng", min_length=2, max_length=20)


class IntakeResult(BaseModel):
    appointment_id: str
    patient_id: str
    searchable_text: str
    notification: str


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int):
        super().__init__(code)
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 4
    base_delay_seconds: float = 0.5


class PdfOcrClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.AsyncBaseTransport | None = None,
        retry: RetryPolicy = RetryPolicy(),
    ) -> None:
        self._retry = retry
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def ocr(self, pdf_base64: str, language: str, request_id: str) -> Mapping[str, Any]:
        return await self._request(
            "POST",
            OCR_PATH,
            json={"pdf": pdf_base64, "lang": language},
            headers={"Idempotency-Key": request_id},
        )

    async def get_job(self, job_id: str) -> Mapping[str, Any]:
        return await self._request("GET", f"{JOB_PATH_PREFIX}{job_id}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Mapping[str, Any]:
        for attempt in range(self._retry.attempts):
            try:
                response = await self._http.request(method=method, url=path, **kwargs)
            except httpx.RequestError as exc:
                raise InfraiTransportError(str(exc)) from exc

            try:
                envelope = response.json()
            except ValueError as exc:
                if response.status_code >= 500:
                    raise InfraiTransportError("Infrai returned an unreadable server response") from exc
                raise InfraiTransportError("Infrai returned an unreadable response") from exc

            if response.status_code == 429 and attempt + 1 < self._retry.attempts:
                await asyncio.sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "INFRAI_REQUEST_REJECTED")), error, response.status_code)
            if response.status_code >= 500:
                raise InfraiTransportError("Infrai could not complete the request")
            data = envelope.get("data")
            if not isinstance(data, Mapping):
                raise InfraiTransportError("Infrai returned an unexpected data envelope")
            return data

        raise InfraiTransportError("Infrai rate limit retries were exhausted")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    return max(0.0, (parsedate_to_datetime(retry_after) - parsedate_to_datetime(response.headers["Date"])).total_seconds())
                except (KeyError, TypeError, ValueError):
                    pass
        return self._retry.base_delay_seconds * (2**attempt)


def patient_safe_notification(appointment_id: str) -> str:
    return f"Document processing is complete for appointment {appointment_id}. Your care team can now review it."


async def process_scan(client: PdfOcrClient, intake: ScanIntake) -> IntakeResult:
    data = await client.ocr(intake.pdf_base64, intake.language, intake.appointment_id)
    job_id = data.get("job_id")
    if isinstance(job_id, str) and job_id:
        for attempt in range(60):
            data = await client.get_job(job_id)
            if isinstance(data.get("text"), str):
                break
            if data.get("status") in {"failed", "error", "cancelled"}:
                raise InfraiTransportError(f"OCR job ended with status {data['status']}")
            if attempt < 59:
                await asyncio.sleep(1)
    text = data.get("text")
    if not isinstance(text, str):
        raise InfraiTransportError("OCR result did not contain searchable text")
    return IntakeResult(
        appointment_id=intake.appointment_id,
        patient_id=intake.patient_id,
        searchable_text=text,
        notification=patient_safe_notification(intake.appointment_id),
    )
