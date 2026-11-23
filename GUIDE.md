# Firaao: Contabo VPS deployment (no Docker)
read this
This deployment runs Django/Gunicorn, PostgreSQL, systemd, and Nginx directly on Ubuntu. It does not install or use Docker. The instructions below assume the domain is `firaao.shop` and use Ubuntu 24.04 LTS.

> **Important for a VPS that already runs another project:** never stop its services, change its firewall/SSH rules, or install a second reverse proxy on ports 80/443. First identify what owns those ports. The Nginx commands below are for an existing host-installed Nginx or a VPS with unused web ports. If the existing proxy is Caddy, Apache, or a Docker container, stop after step 1 and adapt the proxy configuration instead of following the Nginx install/configuration commands blindly.

## 1. Check the existing Contabo server and DNS

At Contabo, make sure inbound TCP ports 80 and 443 are allowed by the VPS firewall. Do not change existing firewall policies just to follow this guide. Add DNS records at your DNS provider:

| Type | Name | Value |
|---|---|---|
| A | `@` | Your Contabo VPS IPv4 address |
| A | `www` | Your Contabo VPS IPv4 address |

If you are not routing IPv6 to this VPS, remove any `AAAA` records for these names. Wait for DNS to resolve before requesting TLS certificates.

SSH into the VPS and inspect it before installing anything:

```bash
ssh root@YOUR_CONTABO_VPS_IP
ss -ltnp | grep -E ':(22|80|443|8000|18080)\b' || true
systemctl is-active nginx || true
systemctl is-active caddy || true
systemctl is-active apache2 || true
free -h
df -h
```

Keep the current project running. If ports 80 or 443 belong to a non-Nginx proxy (including a proxy inside a container), do **not** install or enable another proxy; get the current proxy type/configuration and adapt its site routing first. Firaao's Gunicorn listens only on `127.0.0.1:18080` by default; change `APP_BIND_PORT` in `.env` and the Nginx upstream if that port is in use.

## 2. Install native Ubuntu packages

Run as root, or prefix these commands with `sudo` from an administrator account. This installs packages but does not change firewall or SSH configuration:

```bash
apt update
apt install -y git curl python3 python3-venv python3-dev build-essential \
  libpq-dev postgresql postgresql-contrib nginx certbot python3-certbot-nginx
```

If Nginx was already installed for the other site, keep its existing configuration. Do not overwrite its default site or restart unrelated applications.

Create a deployment account and a separate, unprivileged app-service account. Choose a strong password for the deployment account when prompted; it is used for `sudo`:

```bash
adduser deploy
usermod -aG sudo deploy
useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group firaao
usermod -aG firaao,www-data deploy
install -d -m 755 -o deploy -g deploy /srv/firaao
```

Add your laptop's SSH public key for `deploy` (use your actual key path if different), then test a **new terminal** before continuing:

```bash
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
nano /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Paste your laptop's `.pub` key as the complete contents of `authorized_keys`. From Windows PowerShell, display it with `Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub` (generate one first with `ssh-keygen -t ed25519` if needed). From your laptop:

```bash
ssh deploy@YOUR_CONTABO_VPS_IP
```

Do not disable root/password SSH or modify firewall rules as part of this app deployment.

## 3. Create the PostgreSQL database

On the VPS, connect as `deploy` and set a database password (save it for `.env`):

```bash
sudo -u postgres createuser --pwprompt --no-createdb --no-superuser --no-createrole firaao
sudo -u postgres createdb --owner=firaao firaao
```

Use the password you entered below as `POSTGRES_PASSWORD`. PostgreSQL stays on the server and is not exposed publicly.

## 4. Clone Firaao and configure it

Create a **read-only deploy key** on GitHub and add its public key under the repository's **Settings → Deploy keys**. Then, on the VPS as `deploy`:

```bash
ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Add the displayed key to the private GitHub repository as a read-only deploy key, then:

```bash
git clone git@github.com:birlaG/looprewards.git /srv/firaao/looprewards
cd /srv/firaao/looprewards
cp .env.example .env
chmod 600 .env
nano .env
```

Replace the `CHANGE` values. At minimum configure:

- `SECRET_KEY`: generate with `openssl rand -hex 32` and paste the output.
- `POSTGRES_PASSWORD`: the password created in step 3.
- `SELLER_NAME`, `SELLER_ADDRESS`, applicable `SELLER_GSTIN`, support/grievance contact, legal review date, and actual Contabo data-centre region.
- Razorpay and notification values when those integrations are ready; do not invent credentials.

The domain, hostnames, database name, and media path are prefilled for `firaao.shop`. Keep `DEBUG=0`, `POSTGRES_HOST=127.0.0.1`, and `SECURE_SSL_REDIRECT=1`. Quote values containing spaces (the legal/business defaults are already quoted). Do not add a `REDIS_URL` unless you have separately installed and secured Redis.

Install the Python dependencies and verify Django settings:

```bash
cd /srv/firaao/looprewards
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
mkdir -p media private-media backups
chmod 755 /srv/firaao/looprewards
sudo install -d -m 2750 -o firaao -g www-data /srv/firaao/looprewards/media
sudo install -d -m 2750 -o firaao -g www-data /srv/firaao/looprewards/private-media
sudo chown deploy:firaao .env
chmod 640 .env
set -a
. ./.env
set +a
./venv/bin/python manage.py check
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
```

The committed migrations must be present in Git; do not create migrations on the production server.

## 5. Install the systemd app and daily-job services

Run these commands from the repository directory:

```bash
sudo install -m 644 deploy/firaao.service /etc/systemd/system/firaao.service
sudo install -m 644 deploy/firaao-daily.service /etc/systemd/system/firaao-daily.service
sudo install -m 644 deploy/firaao-daily.timer /etc/systemd/system/firaao-daily.timer
sudo systemctl daemon-reload
sudo systemctl enable --now firaao
sudo systemctl enable --now firaao-daily.timer
sudo systemctl status firaao --no-pager
curl -fsS http://127.0.0.1:18080/healthz
```

Daily reminders, payouts, and retention checks run at about 02:15 India time. `AUTO_PURGE=0` is the safe default: expired-shop deletion is only reported, not applied.

## 6. Route the domain through Nginx and enable HTTPS

**Only do this if Nginx is the VPS's existing host proxy or ports 80/443 are free.** It does not replace existing sites. Install Firaao's separate site file:

```bash
cd /srv/firaao/looprewards
sudo install -m 644 deploy/nginx-firaao.conf /etc/nginx/sites-available/firaao
sudo ln -s /etc/nginx/sites-available/firaao /etc/nginx/sites-enabled/firaao
sudo nginx -t
sudo systemctl reload nginx
```

Confirm DNS is pointing to this server and the HTTP site responds, then request the certificate:

```bash
getent ahostsv4 firaao.shop
curl -I http://firaao.shop/healthz
sudo certbot --nginx -d firaao.shop -d www.firaao.shop --redirect
sudo certbot renew --dry-run
```

The Nginx site serves uploaded media from `/srv/firaao/looprewards/media/` and proxies app requests to localhost. Do not publish the app port or PostgreSQL to the internet.

## 7. Create the administrator and run launch checks

```bash
cd /srv/firaao/looprewards
set -a
. ./.env
set +a
./venv/bin/python manage.py createsuperuser
./venv/bin/python manage.py check --deploy
curl -fsS https://firaao.shop/healthz
```

Open `https://firaao.shop/app/` and `https://firaao.shop/admin/`. Resolve all production-check warnings that apply; security headers such as HSTS are configured in Django. Use a staging domain and Razorpay test credentials before taking real payments.

Before public launch, test the full owner/shop/customer/purchase/reward flows, mobile behavior, profile and bill-photo uploads, password reset, deletion, payment webhooks, and backups/restores. Review `/privacy/`, `/terms/`, `/refund/`, `/pricing/`, and `/contact/`; have a lawyer review legal terms and a CA review invoices/tax treatment.

## 8. Push code updates and upgrade Firaao

On your development computer, run tests and commit the reviewed code/migrations, then push to the Git branch used for deployment (default `main`):

```bash
python manage.py test
git status --short
git add <reviewed-files-and-migrations>
git commit -m "Describe the update"
git push origin main
```

On the VPS, each upgrade is one command:

```bash
ssh deploy@YOUR_CONTABO_VPS_IP
cd /srv/firaao/looprewards
bash ./deploy/deploy.sh
```

The script refuses a dirty checkout, takes a PostgreSQL+media backup first, fast-forwards from `origin/main`, installs updated Python requirements, checks settings, applies migrations, collects static files, restarts Firaao, and checks `/healthz`. If an upgrade fails, it restores the prior code and restarts the previous app version; it does not reverse database migrations. Use additive, backward-compatible migrations.

Manual code rollback to the last successfully deployed revision:

```bash
cd /srv/firaao/looprewards
bash ./deploy/rollback.sh
```

## 9. Backups and recovery

Create a backup now and then schedule one every day:

```bash
cd /srv/firaao/looprewards
bash ./deploy/backup.sh
crontab -e
```

Add this cron line:

```cron
15 3 * * * /usr/bin/bash /srv/firaao/looprewards/deploy/backup.sh >> /srv/firaao/looprewards/backups/backup.log 2>&1
```

Backups include the database, uploaded media, and private UPI payment screenshots; local copies older than 14 days are removed. A server failure can destroy local backups, so configure an encrypted, access-restricted `rclone` remote and `RCLONE_REMOTE` in `.env` for offsite copies. Protect backups as customer data and practice restores on a separate test server.

**Restore is destructive.** Verify the dump path, stop other work, and run:

```bash
cd /srv/firaao/looprewards
bash ./deploy/restore.sh backups/db-DATE.dump backups/media-DATE.tgz backups/proofs-DATE.tgz
```

The script requires typing `RESTORE`, stops Firaao, replaces the selected database contents, restores the media and private screenshot archives, and starts the app. It does not stop or change other VPS projects. Do not use it as a routine rollback.

## 10. Useful operations

```bash
sudo systemctl status firaao --no-pager
sudo journalctl -u firaao -n 100 --no-pager
sudo journalctl -u firaao -f
sudo systemctl restart firaao
sudo systemctl status firaao-daily.timer --no-pager
sudo journalctl -u firaao-daily.service -n 100 --no-pager
sudo nginx -t
df -h
free -h
```

If you change `.env`, restart Firaao with `sudo systemctl restart firaao`. Keep the database password and `SECRET_KEY` backed up securely; never commit `.env`. Monitor available disk, RAM, backups, TLS renewal, and the health endpoint.

## 11. Payments, notifications, and capacity

- Razorpay: configure the webhook at `https://firaao.shop/api/billing/webhook/` for the supported payment and subscription events; use test mode first. Keep API and webhook secrets in `.env`.
- Manual UPI: set `PLATFORM_UPI_ID`; reconcile each payment in the bank statement before approving it in `/admin`.
- SMS/WhatsApp: `NOTIFY_WEBHOOK_URL` must be your provider bridge; set `NOTIFY_SMS=1` only after verifying it.
- Initial worker count is conservative (`WEB_WORKERS=2`). Check Contabo RAM/CPU and existing services before increasing it. Firaao does not require Redis for a basic single-server install; without Redis, per-process throttling/cache is not shared across workers.
- Keep Contabo snapshots and offsite backups. Test the actual restore process before relying on it.

## 12. Troubleshooting

| Problem | Check |
|---|---|
| `502 Bad Gateway` | `sudo systemctl status firaao`; `sudo journalctl -u firaao -n 100 --no-pager`; local `/healthz` |
| HTTP 400 / invalid host | `ALLOWED_HOSTS`, DNS, and Nginx `server_name` |
| CSRF failure | `CSRF_TRUSTED_ORIGINS` includes both `https://firaao.shop` and `https://www.firaao.shop`; Nginx forwards `X-Forwarded-Proto` |
| No TLS certificate | DNS A/AAAA records and Contabo firewall access to ports 80/443; `sudo certbot certificates` |
| Database connection error | `sudo systemctl status postgresql`; verify `POSTGRES_*` in `.env` and that the role/database were created |
| Upload failure | Check `MEDIA_ROOT`, directory ownership/permissions, free disk, and Nginx `client_max_body_size` |
| Upgrade failed | Read `journalctl -u firaao`; deployment script restores old code but migrations are not reversed |

## 13. Project operations and lifecycle

- Customer/owner/staff/agent features and subscription behavior are documented in the app, legal pages, and `README.md`.
- The daily retention command is deliberately a dry run unless `AUTO_PURGE=1`. Review its output and ensure offsite backups and legal retention policy are correct before enabling destructive purges.
- Model changes require a reviewed migration generated during development, committed to Git, and applied by the upgrade script.
- Never edit production code directly on the VPS; develop, test, commit, push, then run the upgrade command.
