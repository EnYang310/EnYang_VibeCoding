import base64
import hashlib
import json
import os
from pathlib import Path

from app.schemas import VoiceSegment, VoiceSubtitle


class VoiceUnavailableError(RuntimeError):
    """Raised when the deployment has not enabled Tencent Cloud TTS yet."""


class TencentVoiceService:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def synthesize_paragraphs(self, paragraphs: list[str]) -> list[VoiceSegment]:
        secret_id = os.getenv("TENCENT_SECRET_ID", "").strip()
        secret_key = os.getenv("TENCENT_SECRET_KEY", "").strip()
        if not secret_id or not secret_key:
            raise VoiceUnavailableError("腾讯云 TTS 尚未配置")

        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.tts.v20190823 import models, tts_client
        except ImportError as exc:
            raise VoiceUnavailableError("服务端缺少腾讯云 TTS SDK") from exc

        voice_type = int(os.getenv("TENCENT_TTS_VOICE_TYPE", "101001"))
        client = tts_client.TtsClient(
            credential.Credential(secret_id, secret_key),
            os.getenv("TENCENT_TTS_REGION", "ap-guangzhou"),
            ClientProfile(httpProfile=HttpProfile(endpoint="tts.tencentcloudapi.com")),
        )
        segments: list[VoiceSegment] = []
        for paragraph in paragraphs:
            text = " ".join(paragraph.split())
            digest = hashlib.sha256(f"v2-timed:{voice_type}:{text}".encode("utf-8")).hexdigest()
            filename = f"{digest}.mp3"
            target = self.cache_dir / filename
            manifest = self.cache_dir / f"{digest}.json"
            if target.exists() and manifest.exists():
                cached = json.loads(manifest.read_text("utf-8"))
                subtitles = [VoiceSubtitle(**item) for item in cached.get("subtitles", [])]
            else:
                request = models.TextToVoiceRequest()
                request.Text = text
                request.SessionId = digest[:32]
                request.ModelType = 1
                request.VoiceType = voice_type
                request.Codec = "mp3"
                request.SampleRate = 16000
                request.Speed = 0.0
                request.Volume = 5.0
                request.EnableSubtitle = True
                response = client.TextToVoice(request)
                target.write_bytes(base64.b64decode(response.Audio))
                subtitles = [
                    VoiceSubtitle(
                        text=item.Text,
                        begin_time=item.BeginTime,
                        end_time=item.EndTime,
                        begin_index=item.BeginIndex,
                        end_index=item.EndIndex,
                    )
                    for item in (response.Subtitles or [])
                    if item.Text and item.EndTime > item.BeginTime
                ]
                manifest.write_text(json.dumps({"subtitles": [item.model_dump() for item in subtitles]}, ensure_ascii=False), "utf-8")
            segments.append(
                VoiceSegment(
                    audio_url=f"/media/voice/{filename}",
                    audio_base64=base64.b64encode(target.read_bytes()).decode("ascii"),
                    subtitles=subtitles,
                )
            )
        return segments
