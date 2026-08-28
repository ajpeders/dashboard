# Homelab Dashboard

A single-page dashboard for the `example.com` homelab. It **auto-discovers**
services from Traefik's router list, shows a live status dot for each one, and
provides on/off toggles for heavy "on-demand" containers (game servers, VMs).

There is no service list to maintain: anything Traefik routes shows up
automatically. `META` in `index.html` is only a presentation overlay (nice name,
icon, category, description) for hosts you want to curate.

```
browser ──(local-only@file)── Traefik ── nginx :80 ─┬─ /                 index.html + dashboard-v2.css
                                                     ├─ /traefik-api/    → Traefik API   (discovery)
                                                     ├─ /probe/<host>    → Traefik       (reachability)
                                                     ├─ /power/          → dashboard-power (start/stop)
                                                     ├─ /status/         → dashboard-power (docker health)
                                                     └─ /data/           → host state dir + repo icons
```

## Quick start

```sh
cp .env.example .env        # set DASHBOARD_DOMAIN
bin/dashboard-icons         # fetch service icons into data/icons/
bin/dashboard-meta          # collect service descriptions from Docker labels
docker compose up -d
```

The dashboard is then served at `https://$DASHBOARD_DOMAIN`, behind Traefik's
`local-only@file` middleware (LAN/VPN only — there is **no** authentication of
any kind, so it must never be exposed publicly).

## Key commands

| Command | What it does |
|---|---|
| `docker compose up -d` | Start `dashboard` + `dashboard-power` |
| `docker compose restart dashboard` | **Apply an edit** to `index.html`, `dashboard-v2.css`, or `default.conf` |
| `docker compose logs -f dashboard-power` | Watch the power sidecar |
| `bin/dashboard-icons` | Download missing icons into `data/icons/` |
| `bin/dashboard-icons --force` | Re-download every icon |
| `bin/dashboard-meta` | Collect names/descriptions from Docker labels → `meta.json` |
| `bin/dashboard-meta --dry-run` | Preview that JSON without writing it |
| `python3 -m compileall -q power` | Syntax-check the sidecar (what CI runs) |

> A file edit needs a **restart**, not `nginx -s reload` — see
> [HOWTO.md](HOWTO.md#applying-a-change-to-indexhtml-css-or-nginx-config).

## Layout

```
index.html          the whole app — legacy inline CSS + all JS
dashboard-v2.css    v2 UI shell, loaded after and overriding the inline styles
default.conf        nginx: static serving + the four proxy routes
docker-compose.yml  dashboard (nginx) + dashboard-power (privileged sidecar)
power/              Flask start/stop backend (allowlist-gated, docker.sock)
bin/dashboard-icons icon fetcher (host-side)
bin/dashboard-meta  name/description collector from Docker labels (host-side)
data/icons/         self-hosted PNGs, served same-origin at /data/icons/
```

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — how discovery, status, and layout work, and why
- [ROADMAP.md](ROADMAP.md) — current state and what's next
- [HOWTO.md](HOWTO.md) — adding services, icons, on-demand toggles, troubleshooting
