# 🔥 StokerCloud → ntfy Hopper Alert  

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Docker](https://img.shields.io/badge/docker-containerized-informational.svg)
![Status](https://img.shields.io/badge/status-production--ready-success.svg)

A lightweight, automated monitoring service that logs into **StokerCloud**, retrieves your boiler's **hopper pellet level**, and sends **ntfy alerts** when pellets are low.  
Runs in a tiny Docker container and automatically recovers from token expiration.

---
## ✨ Features

- 🔐 Logs into **StokerCloud v2 API**  
- 🔁 Automatically renews expired **tokens**  
- 📜 Automatically accepts StokerCloud’s **terms**  
- 📊 Reads hopper level from `frontdata.hoppercontent` (KG)  
- 🚨 Sends notifications via **ntfy** (HTTP or HTTPS)  
- 🔕 Alert throttling (no spam)  
- 🛠 Robust auto-retry logic (never crashes)  
- 🐳 Built with a tiny **Alpine Python** Docker image  
- ⚙️ Fully configurable via environment variables  

---

## 🗂 Project Layout

```text
.
├── Stoker_Scraper.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env            # secrets – do NOT commit to GitHub
├── .gitignore
└── LICENSE         # MIT
```
---
## ⚙️ Configuration via `.env`

Create a `.env` file in the project folder:

```env
# StokerCloud credentials
STOKERCLOUD_USER=your_username
STOKERCLOUD_PASSWORD=your_password

# ntfy server (HTTP supported!)
NTFY_SERVER=http://192.168.1.10:80
NTFY_TOPIC=stoker-alerts

# Hopper thresholds
LOW_THRESHOLD_KG=100
MAX_CAPACITY_KG=500

# Optional settings
CHECK_INTERVAL_SECONDS=300
MIN_ALERT_INTERVAL_MIN=60
LOG_LEVEL=INFO
```
## ⚠️ CAREFUL - Do not commit .env or compose files to GitHub.

---

## 🐳 Running with Docker
1. Build the image
```commandline
docker compose build
```
2. Start the service
```commandline
docker compose up -d
```
3. View logs
```commandline
docker compose logs -f
```
Expected output:
```text
Got token from login
Accepting terms for token
Hopper (frontdata.hoppercontent): 122.0 kg
Hopper OK: 122.0 kg (24.4%), threshold 100 kg
```
If the hopper is below the threshold:
```text
Sending ntfy alert to http://192.168.1.10:80/stoker-alerts
```

### If you want to use a prebuilt Docker image instead of building locally, update the compose like this:
```Yaml
services:
  stokercloud-scraper:
    image: ghcr.io/rolfstevns/stokercloud-ntfy:latest
    restart: unless-stopped
    env_file:
      - .env
```

### Or without .env if you prefer.
```Yaml
services:
  stokercloud-scraper:
    image: ghcr.io/rolfstevns/stokercloud-ntfy:latest
    restart: unless-stopped
    environment:
      STOKERCLOUD_LOGIN_URL: "https://stokercloud.dk/v2/dataout2/login.php"
      STOKERCLOUD_ACCEPT_TERMS_URL: "https://stokercloud.dk/v2/dataout2/acceptterms.php"
      STOKERCLOUD_CONTROLLERDATA_URL: "https://stokercloud.dk/v2/dataout2/controllerdata2.php"
      STOKERCLOUD_USER: "your_username_here"
      STOKERCLOUD_PASSWORD: "your_password_here"
      LOW_THRESHOLD_KG: "100"         ### alert when <= this amount left
      MAX_CAPACITY_KG: "500"          ### for percentage in messages
      CHECK_INTERVAL_SECONDS: "300"   ### 5 minutes in seconds
      NTFY_SERVER: "https://ntfy.sh"
      NTFY_TOPIC: "my-stoker-alerts"
      NTFY_TITLE: "Pellet hopper low"
      NTFY_PRIORITY: "5"
      MIN_ALERT_INTERVAL_MIN: "60"    ### minutes time between alerts
      LOG_LEVEL: "INFO"
```

---
## 🔄 Automatic Token Renewal
#### StokerCloud tokens expire frequently.
##### This service handles it automatically:
- Detects expired/invalid token
- Re-logins
- Accepts terms
- Retries data fetch
- Continues running without interruption
### This makes it reliable for 24/7 operation.

--- 
## ✉️ ntfy Alerts
#### Notifications are sent to:
```php
<NTFY_SERVER>/<NTFY_TOPIC>
```
#### Examples:
```arduino
https://ntfy.sh/mytopic
http://192.168.1.10:80/stoker-alerts
```
#### Notifications include:
- Remaining hopper kg
- Percentage of full capacity
- Configured threshold

---
## 📄 License

This project is licensed under the MIT License.

See the LICENSE file for details.