# DigitalOcean Reverse Proxy Setup with Caddy and Tailscale

This guide documents the complete setup of a reverse proxy on DigitalOcean using Caddy and Tailscale to securely expose home services to the internet.

## Architecture Overview

```
Internet → subdomain.your-domain.com → Caddy (DigitalOcean) → Tailscale → Home Service
```

- **DigitalOcean Droplet**: Public reverse proxy server
- **Caddy**: Web server with automatic HTTPS and reverse proxy
- **Tailscale**: Private mesh VPN for secure communication
- **Cloudflare**: DNS management and SSL certificates
- **Home Service**: Any web service running at home

## Prerequisites

- DigitalOcean droplet (Ubuntu 22.04 LTS)
- Domain name managed by Cloudflare
- Tailscale account
- Home service running with Tailscale installed

## Step 1: Initial Server Setup

### Create DigitalOcean Droplet
- **OS**: Ubuntu 22.04 LTS
- **Size**: Basic ($6/month recommended)
- **Features**: Enable IPv6
- **Authentication**: SSH keys

### Update System
```bash
sudo apt update && sudo apt upgrade -y
```

## Step 2: Install and Configure Tailscale

### Install Tailscale
```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale with proper settings
sudo tailscale up --accept-routes --accept-dns
```

### Verify Tailscale Connection
```bash
# Check status
sudo tailscale status

# Test connectivity to home server
ping -c 3 HOME_SERVICE_TAILSCALE_IP
curl -I http://HOME_SERVICE_TAILSCALE_IP:PORT
```

## Step 3: Install Caddy

### Install Caddy from Official Repository
```bash
# Install required packages
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https

# Add Caddy repository
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list

# Update package list and install Caddy
sudo apt update
sudo apt install caddy
```

### Enable Caddy Service
```bash
sudo systemctl enable caddy
sudo systemctl start caddy
```

## Step 4: Configure Cloudflare

### Create Cloudflare API Token
1. Go to https://dash.cloudflare.com/
2. Navigate to "My Profile" → "API Tokens"
3. Create a custom token with:
   - **Zone** → `Zone:Read`
   - **Zone** → `DNS:Edit`
   - **Zone Resources**: Include → Specific zone → your-domain.com

### Update DNS Record
1. Go to Cloudflare DNS settings
2. Create/update A record:
   - **Name**: `service` (or desired subdomain)
   - **IPv4 address**: Your droplet's public IP
   - **TTL**: Auto

## Step 5: Install Cloudflare DNS Plugin

### Add Cloudflare Plugin
```bash
sudo caddy add-package github.com/caddy-dns/cloudflare
```

If the plugin installation fails, you may need to restart Caddy:
```bash
sudo systemctl restart caddy
```

### Verify Plugin Installation
```bash
caddy list-modules | grep cloudflare
```
You should see `dns.providers.cloudflare` in the output.

## Step 6: Configure Caddy

### Create Environment File for Security
```bash
sudo nano /etc/caddy/cloudflare.env
```

Add your Cloudflare API token:
```
CLOUDFLARE_API_TOKEN=your_actual_cloudflare_api_token_here
```

### Update Systemd Service to Load Environment
```bash
sudo systemctl edit caddy
```

Add the following content:
```ini
[Service]
EnvironmentFile=/etc/caddy/cloudflare.env
```

### Create Caddyfile
```bash
sudo nano /etc/caddy/Caddyfile
```

### Add Configuration Template
```caddyfile
# Cloudflare DNS configuration snippet
(cloudflare) {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
}

# Example service configurations
service.your-domain.com {
    reverse_proxy HOME_SERVICE_TAILSCALE_IP:SERVICE_PORT
    import cloudflare
}

# Multiple services example
# app.your-domain.com {
#     reverse_proxy HOME_APP_TAILSCALE_IP:3000
#     import cloudflare
# }
#
# media.your-domain.com {
#     reverse_proxy HOME_MEDIA_TAILSCALE_IP:8096
#     import cloudflare
# }
```

Replace the following placeholders:
- `service.your-domain.com` with your desired subdomain
- `HOME_SERVICE_TAILSCALE_IP` with your home service's Tailscale IP
- `SERVICE_PORT` with your home service's port number

### Alternative: Using API Token Directly (Less Secure)
If you prefer not to use environment files:
```caddyfile
(cloudflare) {
    tls {
        dns cloudflare YOUR_CLOUDFLARE_API_TOKEN
    }
}

service.your-domain.com {
    reverse_proxy HOME_SERVICE_TAILSCALE_IP:SERVICE_PORT
    import cloudflare
}
```

### Validate Configuration
```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

### Restart Caddy with New Configuration
```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
sudo systemctl status caddy
```

## Step 7: Testing and Verification

### Test Local Connectivity
```bash
# Test HTTP redirect
curl -I http://localhost:80 -H "Host: service.your-domain.com"

# Test Tailscale connectivity
ping -c 2 HOME_SERVICE_TAILSCALE_IP
curl -I http://HOME_SERVICE_TAILSCALE_IP:SERVICE_PORT
```

### Test External Access
```bash
# Test HTTPS
curl -I https://service.your-domain.com

# Verify DNS resolution
dig service.your-domain.com
```

### Browser Test
Visit `https://service.your-domain.com` in your browser.

## Common Service Examples

### Web Applications
```caddyfile
app.your-domain.com {
    reverse_proxy 100.x.x.x:3000    # Node.js, React, etc.
    import cloudflare
}
```

### Media Servers
```caddyfile
jellyfin.your-domain.com {
    reverse_proxy 100.x.x.x:8096    # Jellyfin
    import cloudflare
}

plex.your-domain.com {
    reverse_proxy 100.x.x.x:32400   # Plex
    import cloudflare
}
```

### Home Automation
```caddyfile
home.your-domain.com {
    reverse_proxy 100.x.x.x:8123    # Home Assistant
    import cloudflare
}
```

### Development Tools
```caddyfile
git.your-domain.com {
    reverse_proxy 100.x.x.x:3000    # Gitea
    import cloudflare
}

code.your-domain.com {
    reverse_proxy 100.x.x.x:8080    # VS Code Server
    import cloudflare
}
```

## Troubleshooting

### Common Issues

#### 1. DNS Not Resolving
```bash
# Verify DNS record points to correct droplet IP
dig service.your-domain.com

# Check droplet's public IP
curl ifconfig.me
```

#### 2. SSL Certificate Issues
```bash
# Check Caddy logs
journalctl -u caddy -n 50

# Restart Caddy to retry certificate generation
sudo systemctl restart caddy
```

#### 3. Cloudflare Plugin Not Found
```bash
# Reinstall the plugin
sudo caddy add-package github.com/caddy-dns/cloudflare

# Verify installation
caddy list-modules | grep cloudflare
```

#### 4. Tailscale Connectivity Issues
```bash
# Check Tailscale status
sudo tailscale status

# Restart Tailscale if needed
sudo systemctl restart tailscaled
sudo tailscale up --accept-routes --accept-dns --reset
```

#### 5. Service Not Responding
```bash
# Check if Caddy is listening
sudo ss -tlnp | grep caddy

# Test direct connection to home service
curl -I http://HOME_SERVICE_TAILSCALE_IP:SERVICE_PORT
```

### Useful Commands

```bash
# Caddy management
sudo systemctl status caddy
sudo systemctl restart caddy
journalctl -u caddy -f

# Configuration validation
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile

# Tailscale management
tailscale status
sudo tailscale netcheck

# Testing connectivity
curl -I https://service.your-domain.com
ping HOME_SERVICE_TAILSCALE_IP
```

## Security Considerations

1. **Encrypted Tailscale Tunnel** - All traffic between droplet and home is encrypted
2. **Automatic HTTPS** - Caddy manages SSL certificates automatically
3. **Private Home Network** - Your home IP address remains hidden
4. **Cloudflare Protection** - Benefits from Cloudflare's security features
5. **Environment Variables** - API tokens stored securely

## Adding New Services

To add a new service, simply add a new block to your Caddyfile:

```caddyfile
newservice.your-domain.com {
    reverse_proxy NEW_SERVICE_TAILSCALE_IP:NEW_SERVICE_PORT
    import cloudflare
}
```

Then:
1. Create the DNS record in Cloudflare
2. Reload Caddy: `sudo systemctl reload caddy`

## Maintenance

### Update Caddy
```bash
sudo apt update && sudo apt upgrade caddy
```

### Update Tailscale
```bash
sudo tailscale update
```

### Monitor Services
```bash
# Monitor Caddy
journalctl -u caddy -f

# Monitor Tailscale
sudo journalctl -u tailscaled -f
```

## Benefits of This Setup

- **Security**: No need to expose home services directly to internet
- **Simplicity**: Single point of entry with automatic HTTPS
- **Scalability**: Easy to add new services
- **Reliability**: Leverages Cloudflare's global network
- **Privacy**: Home IP address remains private
- **Flexibility**: Works with any HTTP-based service

Your reverse proxy setup is complete! You can now securely access your home services from anywhere on the internet.
