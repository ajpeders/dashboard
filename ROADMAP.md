# Roadmap

## Current status

The dashboard is deployed and working: auto-discovery, status dots, group
editing, favorites, and on-demand toggles all function. The **v2 UI migration**
is the active piece of work.

| Area | State |
|---|---|
| Traefik auto-discovery | ✅ Done |
| Status dots (Docker health + HTTP probe) | ✅ Done |
| On-demand power toggles | ✅ Done, hardened + network-isolated |
| Group editor / shared layout | ✅ Done |
| Self-hosted icons | ✅ Done (`bin/dashboard-icons`) |
| v2 UI shell | 🟡 Rendering; cascade contract still unpinned |
| Container description collector | ✅ `bin/dashboard-meta` (Docker socket) |
| Docs | ✅ This set |

## Next up

### 1. Install the collector timer, then retire `NAME_OVERRIDE`

Units are ready in `deploy/`; install per
[HOWTO](HOWTO.md#running-it-on-a-schedule). **Must be done on the homelab host**
— the collector reads that host's Docker socket, so it cannot be verified from a
dev machine.

Once it has run there, check the real output:

```sh
bin/dashboard-meta --dry-run | grep -E 'qbit|prowlarr'
```

Expect `qbit.example.com` → `qbittorrent` and `prowlarr.example.com` →
`prowlarr` (**not** `gluetun`). If so, the `qbit` and `prowlarr` entries in
`NAME_OVERRIDE` (`index.html`) are redundant and can be deleted — the collector
resolves them via the Traefik router name instead.

The `hermes` entry must stay regardless: it is a Traefik file-provider route
with no container at all, so nothing can collect it.

### 2. v2 UI cleanup

- **Pin the cascade contract.** The "New" group's gold highlight survives only
  because the legacy selectors outrank v2's (see ARCHITECTURE.md). That is
  accidental, not designed, and a future tidy-up would silently break it. Add a
  comment, or promote the New-group rules into `dashboard-v2.css` deliberately.
- **Finish or abandon the migration.** The inline block still solely owns the
  editor modal, `@keyframes pulse`, `.switch`/`.slider`, and `section.new-section`,
  so it cannot simply be deleted.

### 3. Smaller items

- CI (`.forgejo/workflows/ci.yml`) now checks the CSS mount and syntax-checks
  the `bin/` scripts, but still cannot catch a broken *proxy route* — the class
  of bug that made `/probe/` report false green. Worth wiring the
  throwaway-container recipe from HOWTO.md into CI.
- `checkAll()` re-probes every card every 30s. Fine at ~35 services; worth
  revisiting if the homelab grows.
- `checkAll()` re-probes every card every 30s. Fine at ~35 services; worth
  revisiting if the homelab grows.

## Deliberately not doing

- **Authentication.** The security model is Traefik's `local-only@file` plus
  network isolation. Adding a login would imply the app is safe to expose, which
  it is not.
- **Putting `dashboard-power` back on the `web` network.** See ARCHITECTURE.md.
- **A build step or framework.** The value of one editable file with no
  dependencies outweighs the tidiness a bundler would buy.
## Make this usable by others (added 2026-08-27)

- [ ] Universalize the README / docs / code for outside users: document setup
  from scratch on generic infrastructure, replace homelab-specific assumptions
  (private hostnames, LAN addresses, personal paths and defaults) with
  env-driven configuration plus examples, and keep the public GitHub mirror
  directly runnable.
