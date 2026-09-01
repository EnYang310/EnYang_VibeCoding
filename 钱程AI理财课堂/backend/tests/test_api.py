from fastapi.testclient import TestClient

from app.main import app
from app.schemas import VoiceSegment


client = TestClient(app)


def test_container_health_endpoints_are_available():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_course_api_returns_eight_courses():
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert len(response.json()["courses"]) == 8


def test_course_detail_rejects_unknown_course():
    response = client.get("/api/v1/courses/unknown")
    assert response.status_code == 404


def test_h5_voice_request_uses_url_without_a_duplicate_base64_payload(monkeypatch):
    captured = {}

    class FakeVoiceService:
        voice_type = 101001

        def synthesize_paragraphs(self, paragraphs, *, include_audio_base64=True):
            captured["include_audio_base64"] = include_audio_base64
            return [VoiceSegment(audio_url="/media/voice/test.mp3", audio_base64="aGVsbG8=" if include_audio_base64 else None, subtitles=[])]

    monkeypatch.setattr("app.main.voice_service", FakeVoiceService())
    response = TestClient(app).post(
        "/api/v1/voice/synthesize",
        headers={"X-Qiancheng-Audio-Format": "url"},
        json={"paragraphs": ["这是第一段讲解。"]},
    )

    assert response.status_code == 200
    assert captured["include_audio_base64"] is False
    assert "audio_base64" not in response.json()["segments"][0]
