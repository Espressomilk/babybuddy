<img src="icon-brand-new.png" height="150" align="left">

# Baby Buddy

[![License](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A buddy for babies! Helps caregivers track sleep, feedings, diaper changes,
tummy time and more to learn about and predict baby's needs without (_as much_)
guess work.

> This is a self-hosted, customized fork of
> [Baby Buddy](https://github.com/babybuddy/babybuddy) with additional features
> (e.g. milk stash tracking, procedure records, per-side breastfeeding and
> pumping, Siri quick actions, and a touch-friendly dashboard).

<br clear="left"/>

## 📘 Documentation

Visit [https://docs.baby-buddy.net](https://docs.baby-buddy.net) for full
documentation of the upstream project. Self-hosting and Siri setup for this fork
are described below.

## 🐳 Self-hosting on a NAS (Docker)

The app ships as a single container that runs migrations automatically on start
and stores its data in Docker volumes, so upgrades never touch your data.

### Requirements

- A NAS (or any host) with **Docker** and **Docker Compose** — on Synology this
  is the **Container Manager** package.
- Outbound internet access on the host for the initial image build.

### Setup

1. Copy this repository onto the NAS (clone it, or copy the files into a shared
   folder such as `/volume1/docker/babybuddy`).
2. Edit [`docker-compose.yml`](docker-compose.yml) and set:
   - `SECRET_KEY` — a long random string.
   - `CSRF_TRUSTED_ORIGINS` — the address you'll use, e.g.
     `http://YOUR-NAS-IP:8000` (add `https://yourname.synology.me` too if you use
     a reverse proxy — see below).
3. Build and start it:
   ```bash
   docker compose up -d --build
   ```
4. Create your first account:
   ```bash
   docker exec -it babybuddy python manage.py createsuperuser
   ```
5. Open `http://YOUR-NAS-IP:8000` and sign in.

Your SQLite database and uploaded photos live in the `babybuddy-data` and
`babybuddy-media` volumes and survive rebuilds.

### Updating

```bash
./scripts/backup.sh          # snapshot the database + media first
git pull
docker compose up -d --build # rebuild; migrations run automatically on start
```

> **Build stalls at `apt-get`?** If the build hangs or fails with
> `Temporary failure resolving deb.debian.org`, your Docker build container has
> no DNS. Add `network: host` under `build:` in `docker-compose.yml`, or set
> `"dns": ["1.1.1.1", "8.8.8.8"]` in the host's Docker daemon config.

### Backups & restore

- [`scripts/backup.sh`](scripts/backup.sh) writes a timestamped snapshot of the
  SQLite database and media into `./backups/` and records the current git
  revision (keeps the latest 14).
- [`scripts/restore.sh`](scripts/restore.sh) restores the latest backup by
  default, or a specific one: `./scripts/restore.sh <backup-name>`
  (`--list` shows what's available). It also prints the git revision to check
  out to match the restored data.

### Optional: HTTPS + live dashboard refresh (reverse proxy)

To reach the app at `https://yourname.synology.me`, put it behind Synology's
reverse proxy (**Control Panel → Login Portal → Advanced → Reverse Proxy**)
pointing at `localhost:8000`.

The dashboard refreshes in real time over a **WebSocket** (`/ws/track/…`). Most
reverse proxies drop the upgrade headers by default, which breaks live refresh.
On Synology, edit the proxy rule → **Custom Header → Create → WebSocket** to add:

| Header       | Value                 |
| ------------ | --------------------- |
| `Upgrade`    | `$http_upgrade`       |
| `Connection` | `$connection_upgrade` |

Also add `https://yourname.synology.me` to `CSRF_TRUSTED_ORIGINS`.

## 🗣️ Siri integration

This fork exposes lightweight "quick action" API endpoints designed to be driven
from **iOS Shortcuts / Siri**, so you can log a diaper, bottle, breastfeeding or
pumping session — or ask for a status — by voice.

### 1. Get your API token

In Baby Buddy, open the **user menu → Settings**; your **API key** is shown
there. Requests authenticate with it as an HTTP header:

```
Authorization: Token YOUR-API-KEY
```

### 2. Find your child's slug

Open the child's page — the slug is the last part of the URL
(`/children/<slug>/…`), e.g. `ellie-shi`. (You can also list children at
`/api/children/`.) It's passed to every quick action as `?child=<slug>`.

### 3. Build a Shortcut

Create a Shortcut with a **Get Contents of URL** action:

- **URL:** `https://yourname.synology.me/api/quick/diaper?child=ellie-shi`
  (do **not** add a trailing slash after `diaper`)
- **Method:** `POST` (use `GET` for status)
- **Headers:** `Authorization` → `Token YOUR-API-KEY`
- **Request Body (Form):** e.g. `text` → `solid yellow` (or a dictated variable)

Then add a **Speak Text** action fed by the response so Siri reads the
confirmation back, and give the Shortcut a phrase (e.g. "Log a diaper").

> Tip: for a spoken prompt, use **Dictate Text** → put the result in the `text`
> field. The free-text parser understands English and Chinese (e.g.
> "solid yellow", "大便 黄色").

### Available quick actions

| Action              | Method | Endpoint (append `?child=<slug>`) | Notes |
| ------------------- | ------ | --------------------------------- | ----- |
| Status summary      | GET    | `/api/quick/status`               | Speaks today's totals & last feed |
| Diaper              | POST   | `/api/quick/diaper`               | `text` (free text) or `type`/`color`; `preview=1` to confirm first |
| Bottle feeding      | POST   | `/api/quick/bottle`               | `amount` (ml), `type` (`breast_milk`/`formula`) |
| Breastfeeding       | POST   | `/api/quick/breast/start` · `/stop` | say a side to start (`left`/`right`); stop ends it. One side at a time |
| Pumping             | POST   | `/api/quick/pump/start` · `/stop`   | starts/stops a pumping timer |

Informational responses return HTTP 200 so Siri always reads them aloud.

## Additional documentation

- [Security](/SECURITY.md)
- [License](/LICENSE) (BSD-2 Clause)
