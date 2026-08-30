import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deployment_keeps_secret_server_side_and_builds_the_taro_client():
    assert "MOONSHOT_API_KEY=" in (ROOT / ".env.example").read_text(encoding="utf-8")
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM node:" in dockerfile
    assert "npm run build:h5" in dockerfile
    assert "FROM python:3.12" in dockerfile
    assert "WORKDIR /app/backend" in dockerfile
    assert "USER appuser" in dockerfile
    assert "MOONSHOT_API_KEY" not in dockerfile
    assert 'forwarded_allow_ips="*"' not in (ROOT / "backend" / "app" / "server.py").read_text(encoding="utf-8")


def test_wechat_developer_tools_open_the_taro_output_not_a_webview_shell():
    config = json.loads((ROOT / "client" / "project.config.json").read_text(encoding="utf-8"))
    assert config["compileType"] == "miniprogram"
    assert config["miniprogramRoot"] == "dist/weapp/"
    assert config["appid"] == "touristappid"
    package = json.loads((ROOT / "client" / "package.json").read_text(encoding="utf-8"))
    assert "validate-weapp-api.mjs" in package["scripts"]["build:weapp"]


def test_h5_has_a_source_entrypoint_and_docker_copies_the_build():
    entrypoint = ROOT / "client" / "src" / "index.html"
    assert "<div id=\"app\"></div>" in entrypoint.read_text(encoding="utf-8")
    assert "COPY --from=web /web/dist/h5 ./frontend" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
