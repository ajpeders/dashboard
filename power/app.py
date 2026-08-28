"""Dashboard power backend — the ONLY thing that can start/stop containers on
behalf of the dashboard UI.

Deliberately minimal attack surface:
  - Only containers in ALLOWLIST can be touched (env POWER_ALLOWLIST, comma-sep;
    supports a trailing '*' prefix wildcard, e.g. 'vm-*').
  - Only two verbs: start, stop. No exec, no create, no remove, no image ops.
  - No free-form input reaches Docker: the name is matched against the allowlist
    before any Docker call, and we use the Docker SDK (no shell).
  - Not directly routable — it has no Traefik labels and is reached only via the
    dashboard's nginx proxy (which is already behind local-only). Bind is
    in-container only.

Endpoints:
  GET  /power/<name>          -> {"name","state","running","allowed"}
  POST /power/<name>/start    -> starts it (idempotent)
  POST /power/<name>/stop     -> stops it (idempotent)
  GET  /power/                -> list allowlisted containers + their state
  GET  /healthz               -> ok
"""
import fnmatch
import os

import docker
from flask import Flask, jsonify

ALLOWLIST = [p.strip() for p in os.environ.get("POWER_ALLOWLIST", "").split(",") if p.strip()]
STOP_TIMEOUT = int(os.environ.get("POWER_STOP_TIMEOUT", "20"))

app = Flask(__name__)
_client = docker.from_env()


def _allowed(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in ALLOWLIST)


def _get(name: str):
    """Return the container object, or None. 404-safe."""
    try:
        return _client.containers.get(name)
    except docker.errors.NotFound:
        return None
    except docker.errors.APIError:
        return None


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/status/")
def status_all():
    """Per-container state for the dashboard dots — works for EVERY container,
    including non-web ones (mc/sotf) with no Traefik route to HTTP-probe.
    Returns {name: {status, health}} where health is the Docker healthcheck
    verdict (healthy/unhealthy/starting) or null if the container defines none.
    Not gated by the allowlist — it's read-only status, no control."""
    out = {}
    try:
        for c in _client.containers.list(all=True):
            health = None
            try:
                health = c.attrs.get("State", {}).get("Health", {}).get("Status")
            except (AttributeError, KeyError):
                pass
            out[c.name] = {"status": c.status, "health": health}
    except docker.errors.APIError as e:
        return jsonify({"error": "docker error", "detail": str(e)}), 502
    return jsonify(out)


@app.get("/power/")
def list_power():
    out = []
    for pat in ALLOWLIST:
        # Resolve concrete containers for both exact names and wildcards.
        for c in _client.containers.list(all=True):
            if fnmatch.fnmatch(c.name, pat) and c.name not in (x["name"] for x in out):
                out.append({"name": c.name, "state": c.status, "running": c.status == "running"})
    return jsonify(sorted(out, key=lambda x: x["name"]))


@app.get("/power/<name>")
def status(name):
    if not _allowed(name):
        return jsonify({"error": "not allowed", "name": name}), 403
    c = _get(name)
    if c is None:
        return jsonify({"name": name, "state": "absent", "running": False, "allowed": True}), 404
    return jsonify({"name": name, "state": c.status, "running": c.status == "running", "allowed": True})


@app.post("/power/<name>/<action>")
def power(name, action):
    if action not in ("start", "stop"):
        return jsonify({"error": "action must be start|stop"}), 400
    if not _allowed(name):
        return jsonify({"error": "not allowed", "name": name}), 403
    c = _get(name)
    if c is None:
        return jsonify({"error": "no such container", "name": name}), 404
    try:
        if action == "start":
            c.start()
        else:
            c.stop(timeout=STOP_TIMEOUT)
    except docker.errors.APIError as e:
        return jsonify({"error": "docker error", "detail": str(e.explanation or e)}), 502
    c.reload()
    return jsonify({"name": name, "state": c.status, "running": c.status == "running", "action": action})


if __name__ == "__main__":
    # Behind the dashboard nginx proxy on the internal web network only.
    app.run(host="0.0.0.0", port=8080)
