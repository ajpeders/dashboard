# Architecture

Two containers. `dashboard` is stock nginx serving one HTML file and proxying
four routes; `dashboard-power` is a tiny Flask app that is the only thing
allowed to touch `docker.sock`. All state that outlives a browser lives in the
host state dir (`../../state/dashboard`), not in the repo.

## Components

| Piece | What it is |
|---|---|
| `index.html` | The entire app: legacy inline CSS, all JavaScript, no build step, no dependencies |
| `dashboard-v2.css` | The v2 UI shell, loaded *after* the inline styles and overriding them |
| `default.conf` | Static serving + `/traefik-api/`, `/probe/`, `/power/`, `/status/` |
| `power/app.py` | ~120 lines: allowlisted `start`/`stop`, plus read-only container status |
| `bin/dashboard-meta` | Host-side collector: Docker labels → `meta.json` (names + descriptions) |

## Data flow

```
                    ┌─ /traefik-api/http/routers ─→ Host(`…`) rules ─→ hosts[]
refresh() every 30s ┼─ /data/meta.json  ─→ container names + descriptions
                    ├─ /data/layout.json ─→ shared group layout
                    └─ /status/          ─→ {container: {status, health}}
                                    │
                    hosts[] ─ toService() ─→ svc{}  ─ paint() ─→ DOM
                                    │
                            checkAll() ─→ ping() per card ─→ status dot
```

### Discovery

`discover()` fetches Traefik's router list and pulls every `Host(\`…\`)` out of
the rules, dropping `@internal` routers, non-`websecure` entrypoints, and
anything in `SKIP`. If the Traefik API is unreachable the app falls back to the
static `META` keys and says so in the status line.

`META` is **presentation only**. An unknown host still renders, with a name
derived from its subdomain, under the "New" group.

### Status dots — two sources, deliberately ranked

`ping()` prefers real Docker state and falls back to an HTTP probe:

1. **Docker** (`dockerDot()`) — from `/status/`, keyed by container name. This is
   authoritative and works for containers with no web UI at all (Minecraft,
   game servers). A healthcheck verdict beats the run state, so a
   wedged-but-"running" container reads as down.
2. **HTTP probe** (`/probe/<host>`) — fallback for hosts with no matching
   container, e.g. Traefik file-provider routes like `hermes`.

Two non-obvious rules encoded here:

- **A stopped container's health is ignored.** Docker retains the last health
  verdict after exit, so reading it would report "unhealthy" for something
  that is merely switched off.
- **The probe is server-side on purpose.** Chrome's ORB rejects cross-origin
  `no-cors` HTML responses, so a browser-side fetch reports "down" for services
  that are actually up. `/probe/<host>` bounces through nginx → Traefik so the
  page can read a real HTTP status.

### Why the probe route fails loudly

`/probe/` accepts only `*.example.com`. Anything else hits a guard returning
**421**, because without it a non-matching request fell through to
`try_files → index.html` and returned **200** — which the client read as
"reachable", showing a permanent green dot for a service never contacted.

421 is chosen so the client can distinguish "nginx refused to probe" from "the
service answered": a 404 is ambiguous (a live app can return one, and that
genuinely means it is up), while nothing behind Traefik emits 421.

Widening the regex instead would be worse: unrouted hosts would reach Traefik,
get a 404, and read as "up" again — a quieter version of the same bug.

### Metadata collection

`bin/dashboard-meta` runs on the host and reads container labels over the Docker
socket, emitting `{ "<host>": { "name", "desc" } }`. Hostnames come from each
container's own `traefik.http.routers.*.rule`, so the output tracks what Traefik
actually routes.

The subtlety is **which container a host belongs to**. A container sharing
another's network namespace cannot carry its own Traefik labels, so they live on
the namespace owner — gluetun holds the routers for both qBittorrent and
Prowlarr. Mapping host→labelled container would name both "gluetun" and point
their status dots at the VPN sidecar. So when a router's *name* matches a real
container, that container wins. Descriptions are read only from the resolved
container's own labels, so qBittorrent doesn't inherit gluetun's.

### Layout precedence

```
personal override (localStorage "dash-personal", set via the ✎ editor)
  └→ shared layout (/data/layout.json, server-authored, everyone sees it)
       └→ seedGroups() (deterministic, from META categories in CAT_ORDER)
```

Each refresh reconciles the active layout against reality: hosts that vanished
are dropped, genuinely new hosts are filed under **New** once. Only a *personal*
override is ever written back — the shared layout stays server-authored, so
"organise once" applies to everyone.

Favorites (`dash-favorites`) are per-browser and render a pinned section on top.

## Security model

There is **no authentication anywhere in this app.** Everything rests on
Traefik's `local-only@file` middleware and network isolation.

- `dashboard-power` has **no Traefik route**. It is reachable only through the
  dashboard's own nginx, which is itself behind `local-only@file`.
- It sits on `dashboard-internal` (`internal: true`), **not** the shared `web`
  network. This was a deliberate fix (`1b28af2`): `local-only@file` protects the
  *browser* path, not container-to-container traffic, so while the sidecar sat
  on `web`, any of ~51 containers could `POST /power/<name>/stop` with no
  credential. `internal: true` also cuts outbound egress.
- It mounts `docker.sock` (host-root surface), so the code is deliberately tiny:
  an allowlist (`POWER_ALLOWLIST`), exactly two verbs, no shell, no free-form
  input reaching Docker. Hardened with `read_only`, `cap_drop: ALL`,
  `no-new-privileges`.
- `/status/` is **not** allowlist-gated — it is read-only status with no control.

**If you add a second legitimate caller** (e.g. a Discord bot), attach it to
`dashboard-internal`. Do not put the sidecar back on `web`.

## Notable decisions

- **No build step, no dependencies.** The app is one file you can edit and
  restart. This is why the CSS migration is a layered override rather than a
  rewrite.
- **Icons are self-hosted** (`data/icons/`, served same-origin) so the dashboard
  works offline, on LAN-only devices, and with content blockers. Missing icons
  fall back to built-in inline SVGs, so a failed download is never fatal.
- **`dashboard-v2.css` overrides by specificity + source order, not
  `!important`.** It re-declares the same `:root` custom properties and
  re-specifies only the shell rules it owns. Consequence: the "New" group's gold
  highlight survives only because `section.new-section .card` (0,2,1) outranks
  v2's `.card` (0,1,0). Promoting v2's selector to `main section .card` (0,1,2)
  would silently kill that highlight — the one signal that tells you a new
  service appeared.
