# How-to

## Applying a change to index.html, CSS, or nginx config

```sh
docker compose restart dashboard      # NOT `nginx -s reload`
```

**A reload is not enough, and this will waste your time if you forget it.**
`docker-compose.yml` bind-mounts *individual files*, and a bind mount binds the
**inode**. Most editors write a temp file and rename it over the target, which
creates a *new* inode — the container keeps serving the old one. `nginx -s
reload` then dutifully re-reads the stale original and reports success.

Symptom: your edit is in the file on disk, `git diff` shows it, and the
container behaves as if nothing changed. Confirm with:

```sh
docker compose exec dashboard grep -c "<something you just added>" \
  /etc/nginx/conf.d/default.conf     # 0 means the container has the old inode
```

Applies to `index.html`, `dashboard-v2.css`, and `default.conf`. Icons under
`data/icons/` are a *directory* mount and update without a restart.

## Adding a service

You usually don't. Anything Traefik routes appears automatically under **New**
within 30 seconds, with a name derived from its subdomain.

To curate it, add an entry to `META` in `index.html`:

```js
"myapp.example.com": { name: "My App", icon: "myapp", cat: "Tools",
                          desc: "What it does" },
```

Then fetch its icon and restart:

```sh
bin/dashboard-icons && docker compose restart dashboard
```

`desc` is used both as the tile subtitle and as the tooltip, so write it for a
human. To hide a host entirely (API endpoints, signalling, placeholders), add it
to `SKIP` instead.

## Adding an icon

Icons come from [homarr-labs/dashboard-icons](https://github.com/homarr-labs/dashboard-icons)
(Apache-2.0) and are stored in `data/icons/<name>.png`, matching the `icon:`
field in `META`.

```sh
bin/dashboard-icons            # fetch anything missing
bin/dashboard-icons --force    # re-download everything
```

If upstream names it differently, add an alias in `bin/dashboard-icons`:

```python
ALIASES = { "mylocalname": ["upstream-name", "fallback-name"] }
```

A missing icon is not fatal — the UI falls back to a built-in inline SVG chosen
by `FALLBACK_ICON_BY_NAME`, then by category.

## Adding an on-demand (start/stop) toggle

Two places, both required:

1. **`docker-compose.yml`** — add the container name to `POWER_ALLOWLIST` on the
   `dashboard-power` service. Nothing outside this list can be touched, and `*`
   works as a wildcard (`vm-*`).
2. **`index.html`** — add a `POWER_META` entry for a friendly name and icon:

```js
"my-game-server": { name: "My Game Server", icon: "steam", cat: "Media" },
```

```sh
docker compose up -d dashboard-power    # picks up the new allowlist
docker compose restart dashboard        # picks up POWER_META
```

The panel is driven by the backend's allowlist, **not** Traefik discovery — a
stopped container has no router, so it must be listed here to be startable
again.

## Refreshing service descriptions

Descriptions and the hostname→container mapping come from Docker labels,
collected host-side (the dashboard container has no socket by design):

```sh
bin/dashboard-meta --dry-run    # preview
bin/dashboard-meta              # write ../../state/dashboard/meta.json
```

No restart needed — `meta.json` is a directory mount and is re-fetched every
refresh.

### Running it on a schedule

Units are in `deploy/`. Edit the two paths in the `.service` first, then:

```sh
sudo sed -i "s#/srv/homelab/dashboard#$PWD#g" deploy/dashboard-meta.service
sudo cp deploy/dashboard-meta.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard-meta.timer

systemctl list-timers dashboard-meta.timer   # confirm it's scheduled
sudo systemctl start dashboard-meta.service  # run once now
journalctl -u dashboard-meta.service -n 20   # check the output
```

Every 15 minutes, plus 2 minutes after boot. Container labels only change when
you deploy something, so this does not need to match the dashboard's 30s UI
refresh. A failed run leaves the previous `meta.json` intact (write-then-rename),
so the dashboard keeps serving the last good metadata.

Cron alternative, if you'd rather not use units:

```cron
*/15 * * * * cd /srv/homelab/dashboard && bin/dashboard-meta >/dev/null
```

To give a service a description, label its container:

```yaml
labels:
  - dashboard.desc=What this service does
```

It also reads `org.opencontainers.image.description` from the image, so many
services describe themselves with no work. A service with neither falls back to
the `desc` in `META`.

The collector resolves the **router name** to a real container where possible,
which is how qBittorrent and Prowlarr get their own names instead of `gluetun`
(they share its network namespace, so the Traefik labels live on gluetun). It
prints a `~` note whenever it does this.

## Reorganising groups

Click **✎** in the header. Rename, reorder, add/delete groups, and assign each
service. Saving creates a **personal override stored in this browser only**.

To change what *everyone* sees, edit the shared layout instead:

```sh
$EDITOR ../../state/dashboard/layout.json
```

```json
{ "groups": [ { "name": "Media", "hosts": ["plex.example.com"] } ] }
```

No restart needed — it is fetched per refresh. A browser with a personal
override will keep ignoring it; clear that with `localStorage.removeItem("dash-personal")`
in the console.

## Troubleshooting

**Every service shows "Healthy" but some are clearly down.**
The dot prefers Docker state; check `curl -s localhost/status/` inside the
container. If a card falls back to the HTTP probe, verify the route answers:

```sh
docker compose exec dashboard \
  curl -s -o /dev/null -w '%{http_code}\n' localhost/probe/plex.example.com
```

`421` means the host isn't `*.example.com` and was never probed — the card
will read "not probeable". `502`–`504` means Traefik says the backend is down.

**A card shows the wrong container's name.**
Services sharing another container's network namespace (qBittorrent and Prowlarr
ride the gluetun VPN container) resolve to the wrong name. Add an entry to
`NAME_OVERRIDE` in `index.html`.

**The on-demand panel says "unavailable".**
`/power/` didn't answer. Check the sidecar is up and on the right network:

```sh
docker compose logs --tail=50 dashboard-power
docker inspect dashboard-power -f '{{json .NetworkSettings.Networks}}' | jq keys
```

It must be on `dashboard-internal` and **must not** be on `web`.

**Styling looks broken / half-applied.**
`dashboard-v2.css` isn't loading. It must be mounted in `docker-compose.yml` and
return `text/css`:

```sh
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
  https://$DASHBOARD_DOMAIN/dashboard-v2.css
```

`200 text/html` means the mount is missing and nginx served `index.html` via the
SPA fallback.

## Testing a config change locally

You can run the real image without touching the deployment. The proxy upstreams
won't resolve, so point them at localhost:

```sh
docker run --rm -d --name dash-test -p 8898:80 \
  -v "$PWD/index.html:/usr/share/nginx/html/index.html:ro" \
  -v "$PWD/dashboard-v2.css:/usr/share/nginx/html/dashboard-v2.css:ro" \
  -v "$PWD/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  --add-host traefik:127.0.0.1 --add-host dashboard-power:127.0.0.1 \
  nginx:1.31-alpine

curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8898/probe/plex.example.com
docker rm -f dash-test
```

Discovery will fail and fall back to the static `META` list, which is enough to
exercise layout, grouping, and the probe routes.
