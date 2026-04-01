# Complete Deployment Guide: 0 to 100

*Step-by-step instructions for deploying InSilico Strategy site to Digital Ocean*

---

## Prerequisites

Before starting:
- [ ] Digital Ocean account with payment method
- [ ] Domain name registered (insilicostrategy.com)
- [ ] Local machine with Node.js 18+, npm, Docker
- [ ] Tailscale account (free)
- [ ] Astro project built locally (`npm run build` works)
- [ ] `pv` installed for transfer progress (`brew install pv` on macOS)

> **Note on Docker Build**: This guide uses legacy `docker build` commands. You may see a deprecation warning about buildx - this can be safely ignored. The production VM has buildx installed, and we can migrate anytime without breaking changes. See [Appendix: Migrating to Docker Buildx](#appendix-migrating-to-docker-buildx) for migration instructions.

---

## TLDR: Abridged Steps

0. Local machine setup
   - Generate SSH key, add to ssh-agent
   - Copy `.env.example` to `.env` (fill in IPs later)

1. Create Droplet
   - Add SSH public key during creation
   - Obtain public IP address

2. Configure droplet OS
   - QOL setup (starship prompt, aliases)
   - Install Tailscale → obtain Tailscale IP address
   - **Update `.env` file with both IP addresses**
   - Install Caddy
   - Install Docker, Docker Compose

3. Deploy files to droplet
   - Transfer Docker image (with `pv` progress)
   - Transfer Caddyfile
   - Transfer docker-compose

4. Launch website
   - Reload Caddy
   - Start docker-compose

5. Configure DNS
   - Point domain to droplet IP

---

## Part 0: Local Machine Setup

### Step 0.1: Generate SSH Key

Create a dedicated SSH key for Digital Ocean access:

```bash
# Generate an ed25519 key
ssh-keygen -t ed25519 -C "your-email@example.com" -f ~/.ssh/do_insilicostrategy

# Add the key to your ssh-agent
# (required after every reboot or new terminal session)
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/do_insilicostrategy

# Display the public key — copy this for the DO dashboard
cat ~/.ssh/do_insilicostrategy.pub
```

> **Important**: You must `ssh-add` the key before you can SSH into the droplet. If SSH hangs or is denied, this is the most common cause.

### Step 0.2: Configure SSH Config

Add convenience aliases to `~/.ssh/config` so you don't have to remember IPs:

```
Host insilicostrategy
    HostName <DROPLET_PUBLIC_IP>
    User root
    IdentityFile ~/.ssh/do_insilicostrategy

Host insilicostrategy-ts
    HostName <DROPLET_TAILSCALE_IP>
    User root
    IdentityFile ~/.ssh/do_insilicostrategy
```

Replace `<DROPLET_PUBLIC_IP>` and `<DROPLET_TAILSCALE_IP>` with actual IPs after creating the droplet.

After this, you can connect with just `ssh insilicostrategy` or `ssh insilicostrategy-ts`.

### Step 0.3: Create .env File

```bash
# In project directory
cp .env.example .env
# Edit .env — fill in IPs after droplet creation (Step 1)
```

### Step 0.4: Install pv (Transfer Progress)

```bash
# macOS
brew install pv
```

This gives you a progress bar when transferring Docker images to the droplet. The `justfile` detects `pv` automatically and falls back to no-progress if missing.

---

## Part 1: Infrastructure Setup

### Step 1: Create Digital Ocean Project

- Project name: `insilicostrategy`
- All resources will be organized under this project

### Step 2: Configure Firewalls

We create **two reusable firewalls** in the Digital Ocean dashboard for different server types.

> **Why two firewalls?**
> - Separation of concerns: public vs internal servers
> - Reusable patterns for future infrastructure
> - Easier to manage security rules per service type

Navigate to: **Digital Ocean Dashboard** → **Networking** → **Firewalls** → **Create Firewall**

#### Firewall 1: `http-https` (For Public Web Servers)

**Use case**: Servers that need to serve HTTP/HTTPS traffic (web servers, APIs, reverse proxies)

**Inbound Rules:**

| Type | Protocol | Port Range | Sources |
|------|----------|------------|---------|
| SSH | TCP | 22 | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |
| HTTP | TCP | 80 | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |
| HTTPS | TCP | 443 | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |
| Custom | UDP | 41641 | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |

**Outbound Rules:**

| Type | Protocol | Port Range | Destinations |
|------|----------|------------|--------------|
| All TCP | TCP | All ports | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |
| All UDP | UDP | All ports | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |
| ICMP | ICMP | — | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |

> **Note on UFW**: UFW (the OS-level firewall) is left **inactive** during initial setup. The Digital Ocean firewall handles port filtering at the network level, which is sufficient. UFW can optionally be configured later as defense-in-depth (see [Security Hardening](#security-hardening) in Part 6).

#### Firewall 2: `no-inbound` (For Backend/Internal Servers)

**Use case**: Servers that should NOT be publicly accessible (databases, Redis, internal APIs, background workers)

**Inbound Rules:**

| Type | Protocol | Port Range | Sources |
|------|----------|------------|---------|
| SSH | TCP | 22 | `100.0.0.0/8` (Tailscale only) |
| Custom | UDP | 41641 | All IPv4 `0.0.0.0/0`, All IPv6 `::/0` |

**Outbound Rules:** Same as `http-https` (all outbound allowed).

### Step 3: Launch Ubuntu Droplet

In Digital Ocean Dashboard → **Create** → **Droplets**:

- **Region**: Choose closest to your users
- **Image**: Ubuntu 24.04 LTS
- **Size**: Basic, Regular SSD (start small, resize later)
- **Authentication**: SSH Key — paste the public key from Step 0.1
- **Hostname**: `insilicostrategy`
- **Firewall**: Attach `http-https`
- **Monitoring**: Enable
- **Note the Public IP** → this is `DROPLET_PUBLIC_IP`

**Verify SSH access from local machine:**
```bash
# Make sure your key is loaded
ssh-add -l
# Should list your do_insilicostrategy key

# Connect
ssh root@DROPLET_PUBLIC_IP
```

If SSH hangs, run `ssh-add ~/.ssh/do_insilicostrategy` and retry.

### Step 4: Droplet QOL Setup

Before installing services, set up a comfortable working environment on the droplet.

```bash
ssh root@DROPLET_PUBLIC_IP

# Install starship prompt
curl -sS https://starship.rs/install.sh | sh -s -- -y

# Create starship config directory
mkdir -p ~/.config
```

From your **local machine**, copy the starship config:
```bash
scp deployment/starship.toml root@DROPLET_PUBLIC_IP:~/.config/starship.toml
```

Back on the **droplet**, add to `.bashrc`:
```bash
cat >> ~/.bashrc << 'EOF'

# Starship prompt
eval "$(starship init bash)"
# Tab binding
bind '"\t":menu-complete'
EOF

# Reload
source ~/.bashrc
```

### Step 5: Install and Configure Tailscale

**On droplet:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
# Note the Tailscale IP: 100.x.x.x → DROPLET_TAILSCALE_IP
```

> **On local machine:**
> - Install Tailscale desktop app and authenticate with the same account
> - Test: `ssh root@DROPLET_TAILSCALE_IP`
> - **Update `.env` file** with both IP addresses
> - **Update `~/.ssh/config`** with the actual IPs from Step 0.2

### Step 5.1: Create .env File (On Local Machine)

Now that you have both IP addresses, update your local `.env` file:

```bash
# On local machine, in project directory
# Edit .env and add your IP addresses
# DROPLET_PUBLIC_IP=206.xxx.xx.xxx
# DROPLET_TAILSCALE_IP=100.xx.xxx.x
```

**Verify:**
```bash
cat .env
# Should show both IPs filled in
```

**Note**: The `.env` file is git-ignored and will never be committed.

### Step 6: Install Caddy

```bash
ssh root@DROPLET_TAILSCALE_IP

sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Verify
sudo systemctl status caddy
```

**Note**: Caddy is now installed but not yet configured. The `Caddyfile` lives in your project repository and will be copied to the droplet during deployment.

---

## Part 2: Docker Setup

### Step 7: Install Docker and Docker Compose

```bash
ssh root@DROPLET_TAILSCALE_IP

# Update package index
sudo apt update

# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version

# Test Docker
docker run hello-world
```

**Expected output:**
```
Docker version 24.x.x
Docker Compose version v2.x.x
Hello from Docker! [success message]
```

### Step 8: Create Application Directory

```bash
ssh root@DROPLET_TAILSCALE_IP

mkdir -p /opt/insilicostrategy
cd /opt/insilicostrategy
```

---

## Part 3: Application Deployment

### Step 9: Build and Deploy

> **These files should already exist in your repository:**
> `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `Caddyfile`

We deploy from the local machine to the droplet. Each command shows both the manual version and the `just` shortcut.

**Build Docker image:**
```bash
# (just docker-build)
docker build -t insilicostrategy:latest .
```

**Transfer image to droplet with progress bar:**
```bash
# (just deploy-transfer) — handles pv detection automatically
# Manual version with pv:
IMAGE_SIZE=$(docker image inspect insilicostrategy:latest --format='{{.Size}}')
docker save insilicostrategy:latest | pv -s $IMAGE_SIZE | gzip | \
  ssh root@DROPLET_TAILSCALE_IP "gunzip | docker load"
```

> **Note**: The image transfer takes 3-5 minutes depending on connection speed. The `pv` progress bar shows transfer rate and ETA. Install with `brew install pv` if missing.

**Transfer configuration files:**
```bash
# (just deploy-config)
scp docker-compose.yml root@DROPLET_TAILSCALE_IP:/opt/insilicostrategy/
scp Caddyfile root@DROPLET_TAILSCALE_IP:/etc/caddy/Caddyfile
```

**Reload Caddy and start container:**
```bash
# (just deploy-caddy)
ssh root@DROPLET_TAILSCALE_IP "sudo systemctl reload caddy"

# (just deploy-restart)
ssh root@DROPLET_TAILSCALE_IP "cd /opt/insilicostrategy && docker compose up -d"

# (just deploy-status)
ssh root@DROPLET_TAILSCALE_IP "docker compose -f /opt/insilicostrategy/docker-compose.yml ps"
```

**Or do it all at once:**
```bash
just deploy
```

**Expected output:**
```
NAME              IMAGE                      STATUS         PORTS
web               insilicostrategy:latest   Up 10 seconds  127.0.0.1:4321->4321/tcp
```

### Step 10: Test Locally on Droplet

```bash
ssh root@DROPLET_TAILSCALE_IP

# Test Node.js server responds
curl -I http://localhost:4321
# Expected: HTTP/1.1 200 OK

# Test Caddy proxy
curl -I -H "Host: insilicostrategy.com" http://localhost
# Expected: HTTP/1.1 308 Permanent Redirect to https://insilicostrategy.com/
# This is good! Caddy is correctly redirecting HTTP to HTTPS.
```

---

## Part 4: DNS Configuration

### Step 11: Configure DNS for Caddy & Cloudflare

This is a critical step to get Caddy's automatic HTTPS working correctly with Cloudflare. We point DNS to the droplet, let Caddy get a certificate, then enable the Cloudflare proxy.

**Assumptions:**
- Your domain `insilicostrategy.com` is managed by Cloudflare
- You are in the "DNS" settings for your domain in the Cloudflare dashboard

#### Part A: Initial DNS Setup (DNS Only)

First, we create the records in "DNS only" mode. This allows Caddy to get a certificate from Let's Encrypt directly.

1. **Clean up old records:** Delete any existing `A`, `AAAA`, `CNAME`, or stale `NS` records (e.g. leftover Google `ns-cloud-*` records from domain transfers) for `insilicostrategy.com` and `www`.

2. **Create an `A` record for the root domain:**
    * **Type**: `A`
    * **Name**: `@`
    * **IPv4 address**: `DROPLET_PUBLIC_IP`
    * **Proxy status**: **DNS only** (grey cloud)
    * **TTL**: Auto

3. **Create a `CNAME` record for `www`:**
    * **Type**: `CNAME`
    * **Name**: `www`
    * **Target**: `insilicostrategy.com`
    * **Proxy status**: **DNS only** (grey cloud)
    * **TTL**: Auto

4. **Cloudflare Network settings:** Disable **IPv6 Compatibility** if enabled. This prevents Cloudflare from synthesizing AAAA records that route Let's Encrypt validators through Cloudflare's IPv6 gateway (which returns 502 errors).

#### Part B: Verify Caddy Certificate Acquisition

1. **Ensure Caddy is running:** `ssh root@DROPLET_TAILSCALE_IP "sudo systemctl status caddy"`
2. **Wait 1-2 minutes** for DNS propagation
3. **Watch Caddy logs:**
    ```bash
    ssh root@DROPLET_TAILSCALE_IP "sudo journalctl -u caddy -f"
    # Or: just logs-caddy-follow
    # Look for: "certificate obtained successfully"
    ```
4. **Verify HTTPS from local machine:**
    ```bash
    curl -I https://insilicostrategy.com
    # Expected: HTTP/2 200
    ```

**If certificate acquisition fails**, see [Troubleshooting](#troubleshooting) section below.

#### Part C: Enable Cloudflare Proxy (Orange Cloud)

Once HTTPS works directly:

1. **Change Proxy Status:** In Cloudflare DNS, edit the `A` and `CNAME` records and change to **Proxied** (orange cloud)
2. **Set SSL/TLS Mode:** Cloudflare dashboard → **SSL/TLS** tab → set encryption mode to **Full (Strict)**

### Step 12: Verify Final DNS Configuration

After enabling the proxy, DNS should point to Cloudflare's servers:

```bash
dig insilicostrategy.com +short
# Expected: Cloudflare IPs like 104.21.x.x, 172.67.x.x (NOT your droplet IP)

dig www.insilicostrategy.com +short
# Expected: Same Cloudflare IPs
```

**Check propagation**: https://dnschecker.org

### Step 13: Verify HTTPS Works

```bash
# From local machine
curl -I https://insilicostrategy.com
# Expected: HTTP/2 200

# Check certificate issuer
curl -vI https://insilicostrategy.com 2>&1 | grep -i issuer
# Expected: Let's Encrypt

# Check www
curl -I https://www.insilicostrategy.com
# Expected: HTTP/2 200
```

**In browser:**
- Navigate to https://insilicostrategy.com
- Check for padlock icon (secure connection)
- Open DevTools → Console (should be no errors)

---

## Part 5: Ongoing Maintenance

### Periodic System Updates

```bash
ssh root@DROPLET_TAILSCALE_IP "sudo apt update && sudo apt upgrade -y && docker system prune -f"
# Or: just ssh then run manually
```

### Manual SSL Certificate Renewal (Every ~60-80 Days)

> **Note:** This manual process is required because the Cloudflare proxy intercepts ACME challenges. For a permanent solution, see [Automate SSL Certificate Renewal](#automate-ssl-certificate-renewal) in Part 6.

Let's Encrypt certificates are valid for 90 days. Renew before expiry:

1. **Disable Cloudflare Proxy:** In DNS settings, change both `A` and `CNAME` to **DNS only** (grey cloud)
2. **Wait 1-2 minutes** for propagation
3. **Restart Caddy:**
    ```bash
    ssh root@DROPLET_TAILSCALE_IP "sudo systemctl restart caddy"
    ```
4. **Verify renewal:**
    ```bash
    ssh root@DROPLET_TAILSCALE_IP "sudo journalctl -u caddy -f"
    # Look for "certificate obtained successfully"
    ```
5. **Re-enable Cloudflare Proxy:** Change both records back to **Proxied** (orange cloud)

### Monitoring the System

#### DNS, Proxy, and Caddy Health
```bash
# Check DNS points to Cloudflare IPs
dig insilicostrategy.com +short

# Check site returns 200
curl -I https://insilicostrategy.com

# Check Caddy service
ssh root@DROPLET_TAILSCALE_IP "sudo systemctl status caddy"
# Or: just info-caddy
```

#### Application & Docker Health
```bash
# Container status
just deploy-status
# Or: ssh root@DROPLET_TAILSCALE_IP "docker compose -f /opt/insilicostrategy/docker-compose.yml ps"

# Application logs
just logs-follow
# Or: ssh root@DROPLET_TAILSCALE_IP "docker compose -f /opt/insilicostrategy/docker-compose.yml logs -f"
```

#### Traffic and Analytics
- **Caddy logs**: `ssh root@DROPLET_TAILSCALE_IP "sudo journalctl -u caddy"`
- **Cloudflare Analytics**: Dashboard → **Analytics & Logs** tab for traffic, requests, security events

---

## Part 6: Future Improvements

### Automate SSL Certificate Renewal

Eliminate manual renewal by using a Cloudflare Origin Certificate (valid 15 years):

1. **Generate Certificate:** Cloudflare → **SSL/TLS** → **Origin Server** → Create certificate (15 years)
2. **Copy to Droplet:** Save cert and key, copy to `/etc/caddy/certs/` on droplet
3. **Update Caddyfile:**
    ```caddy
    tls /etc/caddy/certs/insilicostrategy.com.pem /etc/caddy/certs/insilicostrategy.com.key
    ```
4. **Deploy and Reload:** `just deploy-caddy`

### Security Hardening

#### Step A: Lock SSH to Tailscale Only

**⚠️ CRITICAL**: Verify Tailscale access works before this step!

```bash
ssh root@DROPLET_TAILSCALE_IP  # must work first!
```

**Update Digital Ocean Firewall:**

1. Digital Ocean dashboard → **Networking** → **Firewalls**
2. Edit firewall: `http-https`
3. **Inbound Rules** → SSH (port 22):
   - Remove "All IPv4" and "All IPv6"
   - Add source: `100.0.0.0/8` (Tailscale range)
4. Save and test: `ssh root@DROPLET_PUBLIC_IP` should now be blocked, `ssh root@DROPLET_TAILSCALE_IP` still works

#### Step B: Configure UFW Firewall (Optional, Defense-in-Depth)

UFW adds OS-level firewall rules on top of the Digital Ocean network firewall:

```bash
ssh root@DROPLET_TAILSCALE_IP
sudo ufw allow from 100.0.0.0/8 to any port 22 proto tcp
sudo ufw allow 41641/udp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable

# Verify
sudo ufw status verbose
```

#### Step C: Install fail2ban
```bash
ssh root@DROPLET_TAILSCALE_IP "sudo apt install -y fail2ban && sudo systemctl enable --now fail2ban"
```

#### Step D: Enable Automatic Security Updates
```bash
ssh root@DROPLET_TAILSCALE_IP "sudo apt install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades"
```

### Deployment Automation

This project uses [Just](https://github.com/casey/just) for deployment automation. The `justfile` in the project root contains all commands.

```bash
just --list   # See all available commands
just deploy   # Full deployment to production
```

### Automated Backups & Log Rotation

#### Log Rotation

Add to `/etc/docker/daemon.json` on the droplet:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```
Then restart Docker: `sudo systemctl restart docker`.

---

## Troubleshooting

**Site not loading?**
```bash
dig insilicostrategy.com +short              # Check DNS
just deploy-status                            # Check container
ssh root@DROPLET_TAILSCALE_IP "systemctl status caddy"  # Check Caddy
```

**SSL certificate not obtained?**
- Check Caddy logs: `just logs-caddy-follow`
- Verify DNS is grey cloud (DNS only) in Cloudflare — orange cloud blocks ACME challenges
- Disable Cloudflare IPv6 Compatibility (Network tab) — prevents AAAA synthesis that routes Let's Encrypt through Cloudflare
- Clear stale ACME state and restart:
  ```bash
  ssh root@DROPLET_TAILSCALE_IP "sudo systemctl stop caddy && \
    sudo rm -rf /var/lib/caddy/.local/share/caddy/acme/ \
    /var/lib/caddy/.config/caddy/autosave.json && \
    sudo systemctl start caddy"
  ```
- Watch logs for `"certificate obtained successfully"` from `acme-v02.api.letsencrypt.org` (production, NOT staging)

**Can't SSH?**
- Ensure key is loaded: `ssh-add -l` (if missing: `ssh-add ~/.ssh/do_insilicostrategy`)
- Use Digital Ocean web console: Dashboard → Droplet → **Access** → **Launch Console**
- Check Tailscale: `tailscale status`

---

## Appendix: Migrating to Docker Buildx

(This section remains unchanged)
