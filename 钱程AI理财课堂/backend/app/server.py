import os

import uvicorn


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    trusted_proxies = os.getenv("TRUSTED_FORWARDED_IPS", "").strip()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=bool(trusted_proxies),
        forwarded_allow_ips=trusted_proxies or "127.0.0.1",
    )


if __name__ == "__main__":
    main()
