"""Give this box's one tenant an app user, an API key and its shared dataset. Idempotent.

Runs INSIDE the ragflow container (its venv has the RSA library RAGFlow's login needs), talking to the API
(9380) and admin server (9381) on loopback, where the tunnel's /api/v1/admin block does not apply:

    docker exec -i <ragflow> /ragflow/.venv/bin/python - < deploy/bebuilt/tenant-setup.py

Reads from the environment (box-setup.sh passes them from /etc/bebuilt/ragflow-secrets.env):
    ADMIN_DEFAULT_PASSWORD, RAGFLOW_APP_PASSWORD, DEFAULT_SUPERUSER_EMAIL (default admin@ragflow.io),
    RAGFLOW_APP_EMAIL (default ask-app@tenant.local), RAGFLOW_EMBEDDING_MODEL (unset: no dataset yet, since
    the model can only be chosen once, from the client's own sample)
Prints one JSON line: {"api_key", "dataset_id", "embedding_model", "app_user"}.

The embedding model is fixed once the dataset holds content (D6), so an existing dataset is never touched:
if its model differs from the one asked for, this fails instead of carrying on.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

API = "http://127.0.0.1:9380"
ADMIN = "http://127.0.0.1:9381"
DATASET = "shared"
TOKEN_NAME = "bebuilt-app"


def env(name, default=None):
    v = os.environ.get(name, default)
    if not v:
        sys.exit(f"tenant-setup: {name} is not set")
    return v


def encrypt(password):
    # Mirrors web/src/utils/index.ts rsaPsw: RSA-PKCS1v1.5(base64(password)) with conf/public.pem.
    key = RSA.importKey(open("/ragflow/conf/public.pem").read())
    return base64.b64encode(PKCS1_v1_5.new(key).encrypt(base64.b64encode(password.encode()))).decode()


def call(method, url, body=None, auth=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("content-type", "application/json")
    if auth:
        req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.headers


def login(base, path, email, password):
    data, headers = call("POST", f"{base}{path}", {"email": email, "password": encrypt(password)})
    auth = headers.get("Authorization")
    if data.get("code") not in (0, None) or not auth:
        sys.exit(f"tenant-setup: login to {path} as {email} failed: {data.get('message')}")
    return auth


def main():
    superuser = os.environ.get("DEFAULT_SUPERUSER_EMAIL") or "admin@ragflow.io"
    app_email = os.environ.get("RAGFLOW_APP_EMAIL") or "ask-app@tenant.local"
    app_password = env("RAGFLOW_APP_PASSWORD")
    # No model chosen yet (a new client before its sample test): make the user and key, no dataset (D6).
    model = os.environ.get("RAGFLOW_EMBEDDING_MODEL")

    admin = login(ADMIN, "/api/v1/admin/login", superuser, env("ADMIN_DEFAULT_PASSWORD"))
    found, _ = call("GET", f"{ADMIN}/api/v1/admin/users/{app_email}", auth=admin)
    if found.get("code") != 0 or not found.get("data"):
        made, _ = call("POST", f"{ADMIN}/api/v1/admin/users", {"username": app_email, "password": encrypt(app_password), "role": "user"}, auth=admin)
        if made.get("code") != 0:
            sys.exit(f"tenant-setup: creating {app_email} failed: {made.get('message')}")

    user = login(API, "/api/v1/auth/login", app_email, app_password)
    tokens, _ = call("GET", f"{API}/api/v1/system/tokens", auth=user)
    key = next((t["token"] for t in tokens.get("data") or [] if t.get("name") == TOKEN_NAME), None)
    if not key:
        made, _ = call("POST", f"{API}/api/v1/system/tokens", {"name": TOKEN_NAME}, auth=user)
        key = (made.get("data") or {}).get("token")
        if not key:
            sys.exit(f"tenant-setup: creating the API key failed: {made.get('message')}")

    bearer = f"Bearer {key}"
    listed, _ = call("GET", f"{API}/api/v1/datasets?name={DATASET}", auth=bearer)
    existing = [d for d in listed.get("data") or [] if d.get("name") == DATASET]
    if not model:
        # No model named: never create one, but never forget one that exists either.
        ds = existing[0] if existing else {"id": None, "embedding_model": None}
        print(json.dumps({"api_key": key, "dataset_id": ds["id"], "embedding_model": ds.get("embedding_model"), "app_user": app_email}))
        return
    if existing:
        ds = existing[0]
        if ds.get("embedding_model") != model:
            sys.exit(f"tenant-setup: dataset '{DATASET}' uses {ds.get('embedding_model')}, not {model}; the model cannot change once a dataset exists (D6)")
    else:
        made, _ = call("POST", f"{API}/api/v1/datasets", {"name": DATASET, "embedding_model": model, "chunk_method": "naive", "permission": "me"}, auth=bearer)
        if made.get("code") != 0:
            sys.exit(f"tenant-setup: creating dataset failed: {made.get('message')}")
        ds = made["data"]

    print(json.dumps({"api_key": key, "dataset_id": ds["id"], "embedding_model": ds.get("embedding_model"), "app_user": app_email}))


if __name__ == "__main__":
    main()
