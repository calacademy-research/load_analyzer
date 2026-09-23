"""Minimal ASGI app: answer every plain-HTTP request with a 301 to the same
URL on https. Served by a second uvicorn on :80 (see docker_start.sh) so the
old http://ibss-crontab/ links keep working after the dashboard moved to :443.
"""


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    host = b""
    for name, value in scope.get("headers", []):
        if name == b"host":
            host = value.split(b":", 1)[0]
            break
    if not host:
        host = b"ibss-crontab.calacademy.org"
    target = b"https://" + host + scope["raw_path"]
    if scope.get("query_string"):
        target += b"?" + scope["query_string"]
    await send({"type": "http.response.start", "status": 301,
                "headers": [(b"location", target), (b"content-length", b"0")]})
    await send({"type": "http.response.body", "body": b""})
