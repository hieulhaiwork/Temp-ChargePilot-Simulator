"""Dịch vụ nhận dạng giọng nói tiếng Việt đa vùng miền (Bắc / Trung / Nam) cho Trợ lý sạc.

Kiến trúc có điểm cắm fallback rõ ràng:
  1. Primary (`ASR_PROVIDER=gemini`): gửi audio trực tiếp tới Gemini Audio-in với prompt
     ngữ cảnh bãi sạc EV (hiểu tốt giọng Bắc, Trung, Nam và thuật ngữ AC/DC/VF3/VF8/VF9/% pin).
  2. Fallback slot (`ASR_FALLBACK_PROVIDER=local_phowhisper`): điểm chờ sẵn để cắm server VM
     chạy `vinai/PhoWhisper-medium` hoặc `vinai/PhoWhisper-large` sau này khi có VM đủ RAM/GPU.
  3. Mock (`ASR_PROVIDER=mock` hoặc `LLM_PROVIDER=mock`): trả chuỗi mẫu ổn định cho test offline.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging

import httpx

from src.config import Settings, get_settings
from src.models.api import ErrorCode
from src.models.schemas import TranscribeResponse
from src.services.errors import DomainError

logger = logging.getLogger("chargepilot.services.speech")

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB (~30-60s voice clip)
ALLOWED_MIME_PREFIXES = (
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
)

_VIETNAMESE_EV_TRANSCRIBE_PROMPT = (
    "Bạn là bộ nhận dạng giọng nói tiếng Việt chuyên sâu, am hiểu giọng cả 3 miền "
    "(Bắc: Hà Nội/Hải Phòng; Trung: Nghệ An/Hà Tĩnh/Huế/Quảng Nam/Đà Nẵng; Nam: TP.HCM/Miền Tây). "
    "Hãy chép lại CHÍNH XÁC lời người nói thành tiếng Việt chuẩn có dấu, giữ đúng các con số phần trăm pin "
    "(vd: 32%, 80%), giờ giấc (vd: 7h sáng mai, 22:00 tối nay), và thuật ngữ trạm sạc xe điện "
    "(AC, DC, sạc nhanh, sạc chậm, ở bãi, đặt trước, VF3, VF8, VF9). "
    "Chỉ trả về DUY NHẤT câu văn bản người dùng đã nói, không thêm lời giải thích, không bọc dấu ngoặc kép."
)


def _clean_mime(mime_type: str) -> str:
    base = (mime_type or "audio/webm").split(";")[0].strip().lower()
    if not any(base == allowed for allowed in ALLOWED_MIME_PREFIXES):
        raise DomainError(
            ErrorCode.HTTP_ERROR,
            f"Định dạng âm thanh không được hỗ trợ ({base}). Hỗ trợ: webm, mp4, ogg, wav, mp3.",
        )
    return base


def _decode_audio(audio_base64: str) -> bytes:
    raw_b64 = audio_base64.strip()
    if "," in raw_b64 and raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        data = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DomainError(ErrorCode.HTTP_ERROR, "Dữ liệu âm thanh base64 không hợp lệ.") from exc
    if not data:
        raise DomainError(ErrorCode.HTTP_ERROR, "Bản ghi âm trống, vui lòng thử nói lại.")
    if len(data) > MAX_AUDIO_BYTES:
        raise DomainError(ErrorCode.HTTP_ERROR, "Bản ghi âm vượt quá giới hạn 5 MB.")
    return data


async def _transcribe_gemini(audio_bytes: bytes, mime_type: str, settings: Settings) -> str:
    """Gọi trực tiếp Gemini generateContent với inline_data audio — truyền key qua header, chỉ thử model gemini-*."""
    api_key = (settings.google_api_key or settings.openai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("Thiếu API key để gọi Gemini Audio-in.")
    if api_key.startswith("sk-"):
        raise RuntimeError("OPENAI_API_KEY (sk-...) không dùng được cho Gemini Audio-in; cần đặt GOOGLE_API_KEY.")

    raw_candidates = [
        settings.asr_model,
        *(m.strip() for m in settings.asr_fallback_models.split(",") if m.strip()),
        settings.model_classify,
    ]
    candidates_models: list[str] = []
    for m in raw_candidates:
        if m and m.startswith("gemini-") and m not in candidates_models:
            candidates_models.append(m)
    if not candidates_models:
        candidates_models = ["gemini-3.8-flash"]

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _VIETNAMESE_EV_TRANSCRIBE_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 256},
    }
    headers = {"x-goog-api-key": api_key}
    last_exc: Exception | None = None
    body: dict = {}
    async with httpx.AsyncClient(timeout=settings.asr_timeout_seconds) as client:
        for model in candidates_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(2):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    body = resp.json()
                    last_exc = None
                    break
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    code = exc.response.status_code
                    logger.warning("Gemini ASR model '%s' returned HTTP %s (attempt %d)", model, code, attempt + 1)
                    if code == 503 and attempt == 0:
                        await asyncio.sleep(0.8)
                        continue
                    if code in (404, 429, 500, 502, 503):
                        break
                    raise RuntimeError(f"Gemini ASR returned HTTP {code}") from None
            if last_exc is None:
                break
    if last_exc is not None:
        status_code = last_exc.response.status_code if isinstance(last_exc, httpx.HTTPStatusError) else "error"
        raise RuntimeError(f"Gemini ASR failed ({status_code})") from None

    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini Audio-in không trả về candidate nào.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = " ".join(str(p.get("text") or "").strip() for p in parts if p.get("text")).strip()
    if not text:
        raise RuntimeError("Không nhận dạng được lời nói từ bản ghi âm.")
    return text


async def _transcribe_local_phowhisper(audio_bytes: bytes, mime_type: str, settings: Settings) -> str:
    """Điểm cắm (fallback slot) cho model nội bộ `vinai/PhoWhisper-medium` / `large` trên VM riêng.

    Chưa triển khai inference cục bộ ở phiên bản hiện tại (máy local 8 GB RAM không GPU).
    Khi dựng xong VM chạy PhoWhisper, chỉ cần đặt `LOCAL_ASR_BASE_URL` (vd http://<vm-ip>:8001/transcribe)
    và `ASR_FALLBACK_PROVIDER=local_phowhisper` trong `.env`.
    """
    if not settings.local_asr_base_url:
        raise NotImplementedError(
            "Local PhoWhisper fallback chưa cấu hình LOCAL_ASR_BASE_URL — sẵn sàng cắm VM vinai/PhoWhisper-medium/large."
        )
    payload = {
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        "mime_type": mime_type,
        "language": "vi",
    }
    async with httpx.AsyncClient(timeout=settings.asr_timeout_seconds) as client:
        resp = await client.post(settings.local_asr_base_url, json=payload)
        resp.raise_for_status()
        body = resp.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise RuntimeError("Local PhoWhisper trả về văn bản rỗng.")
    return text


async def _transcribe_mock(audio_bytes: bytes, mime_type: str, settings: Settings) -> str:
    return "Mình đang ở bãi, pin còn 42%, cần sạc lên 80% trước 7h sáng mai"


async def _run_provider(provider: str, audio_bytes: bytes, mime_type: str, settings: Settings) -> str:
    if provider == "gemini":
        return await _transcribe_gemini(audio_bytes, mime_type, settings)
    if provider == "local_phowhisper":
        return await _transcribe_local_phowhisper(audio_bytes, mime_type, settings)
    if provider == "mock":
        return await _transcribe_mock(audio_bytes, mime_type, settings)
    raise ValueError(f"ASR provider không hợp lệ: {provider}")


async def transcribe_audio(audio_base64: str, mime_type: str = "audio/webm") -> TranscribeResponse:
    """Chuyển âm thanh tiếng Việt đa vùng miền thành văn bản, tự động fallback nếu API chính lỗi."""
    settings = get_settings()
    clean_mime = _clean_mime(mime_type)
    audio_bytes = _decode_audio(audio_base64)

    primary = "mock" if settings.llm_provider == "mock" and settings.asr_provider == "gemini" else settings.asr_provider
    try:
        text = await _run_provider(primary, audio_bytes, clean_mime, settings)
        return TranscribeResponse(text=text, provider=primary, fallback_used=False)
    except Exception as primary_exc:
        logger.warning("ASR primary '%s' failed (%s)", primary, type(primary_exc).__name__)
        fallback = settings.asr_fallback_provider
        if fallback != "none" and fallback != primary:
            try:
                text = await _run_provider(fallback, audio_bytes, clean_mime, settings)
                logger.info("ASR fallback '%s' succeeded after primary '%s' failure", fallback, primary)
                return TranscribeResponse(text=text, provider=fallback, fallback_used=True)
            except Exception as fb_exc:
                logger.error("ASR fallback '%s' also failed (%s)", fallback, type(fb_exc).__name__)

        raise DomainError(
            ErrorCode.LLM_UNAVAILABLE,
            "Nhận dạng giọng nói tạm thời không khả dụng. Bạn vui lòng nhập văn bản trực tiếp nhé.",
        ) from primary_exc
