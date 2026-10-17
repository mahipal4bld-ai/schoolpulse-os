"""Emergent Object Storage wrapper (server-side only)."""
import logging
import os

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "schoolpulse-os")
_storage_key = None

# CI/test only: in-process object store so GitHub Actions never needs live storage credentials.
# Refused outside APP_ENV=test|ci so production can never silently store files in memory.
_MEMORY = os.environ.get("STORAGE_BACKEND", "").lower() == "memory"
if _MEMORY and os.environ.get("APP_ENV", "production").lower() not in {"test", "ci"}:
    raise RuntimeError("STORAGE_BACKEND=memory is only allowed with APP_ENV=test or APP_ENV=ci")
_mem: dict[str, tuple[bytes, str]] = {}


def init_storage():
    global _storage_key
    if _MEMORY:
        return "memory"
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _reset():
    global _storage_key
    _storage_key = None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if _MEMORY:
        _mem[path] = (data, content_type)
        return {"path": path, "size": len(data)}
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 503:
        _reset()
        key = init_storage()
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    if _MEMORY:
        if path not in _mem:
            raise KeyError(path)
        return _mem[path]
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 503:
        _reset()
        key = init_storage()
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
