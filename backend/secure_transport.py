"""
secure_transport.py - end-to-end encryption between the backend and the dashboard.

At login the backend puts a random session id (sid) in the token and gives the browser the
matching 32-byte session key (crypto_store.session_key). For every request that carries
that token:
  - JSON responses are sent as {"__ag_enc": "<base64 nonce + AES-256-GCM ciphertext>"};
    the frontend decrypts them (frontend/src/api/client.ts).
  - Request bodies marked with the header X-AG-Enc: 1 arrive as {"__ag_enc": "..."} and
    are decrypted here before FastAPI reads them.
Not encrypted: requests without a token (login, the detector, the wristband), files
(clips, photos) and downloads (Content-Disposition, e.g. the admin backup).
"""

import json

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from auth import decode_access_token
from crypto_store import decrypt_bytes, encrypt_bytes, session_key

ENC_FIELD = "__ag_enc"


def _key_for(headers):
    auth = headers.get(b"authorization", b"").decode("latin-1")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_access_token(auth[len("Bearer "):])
    if not payload or not payload.get("sid"):
        return None
    return AESGCM(session_key(payload["sid"]))


async def _send_json(send, status, data):
    body = json.dumps(data).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class SecureTransport:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        aes = _key_for(headers)

        if aes is None:
            return await self.app(scope, receive, send)

        # ---- request: decrypt an encrypted JSON body ----
        if headers.get(b"x-ag-enc") == b"1":
            body = b""
            while True:
                msg = await receive()
                body += msg.get("body", b"")
                if not msg.get("more_body"):
                    break
            try:
                plain = decrypt_bytes(aes, json.loads(body)[ENC_FIELD])
            except Exception:
                return await _send_json(send, 400, {"detail": "The request could not be decrypted. Log in again."})

            sent = False

            async def receive_plain():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": plain, "more_body": False}
                return await receive()

            scope = dict(scope, headers=[(k, v) for k, v in scope["headers"] if k.lower() != b"content-length"]
                         + [(b"content-length", str(len(plain)).encode())])
            receive = receive_plain

        # ---- response: encrypt JSON bodies ----
        start = None
        passthrough = False
        chunks = []

        async def send_encrypted(msg):
            nonlocal start, passthrough
            if msg["type"] == "http.response.start":
                h = {k.lower(): v for k, v in msg.get("headers", [])}
                if not h.get(b"content-type", b"").startswith(b"application/json") or b"content-disposition" in h:
                    passthrough = True
                    return await send(msg)
                start = msg
                return
            if msg["type"] == "http.response.body" and not passthrough:
                chunks.append(msg.get("body", b""))
                if msg.get("more_body"):
                    return
                body = json.dumps({ENC_FIELD: encrypt_bytes(aes, b"".join(chunks))}).encode()
                new_headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
                new_headers.append((b"content-length", str(len(body)).encode()))
                await send(dict(start, headers=new_headers))
                return await send({"type": "http.response.body", "body": body})
            return await send(msg)

        return await self.app(scope, receive, send_encrypted)
