from fastapi.testclient import TestClient

from app.main import app


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
