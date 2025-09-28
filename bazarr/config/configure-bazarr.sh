#!/bin/bash

# Configuration file path
CONFIG_FILE="/config/config/config.yaml"

# Check if config file exists and update API keys
if [ -f "$CONFIG_FILE" ]; then
    echo "Configuring Bazarr with API keys and settings..."

    # Update Sonarr settings
    if [ ! -z "$SONARR_API_KEY" ]; then
        sed -i "s/sonarr_apikey: .*/sonarr_apikey: $SONARR_API_KEY/" "$CONFIG_FILE"
        sed -i "s/sonarr_ip: .*/sonarr_ip: sonarr/" "$CONFIG_FILE"
        sed -i "s/sonarr_port: .*/sonarr_port: 8989/" "$CONFIG_FILE"
        sed -i "s/sonarr_ssl: .*/sonarr_ssl: false/" "$CONFIG_FILE"
        echo "Updated Sonarr configuration"
    fi

    # Update Radarr settings
    if [ ! -z "$RADARR_API_KEY" ]; then
        sed -i "s/radarr_apikey: .*/radarr_apikey: $RADARR_API_KEY/" "$CONFIG_FILE"
        sed -i "s/radarr_ip: .*/radarr_ip: radarr/" "$CONFIG_FILE"
        sed -i "s/radarr_port: .*/radarr_port: 7878/" "$CONFIG_FILE"
        sed -i "s/radarr_ssl: .*/radarr_ssl: false/" "$CONFIG_FILE"
        echo "Updated Radarr configuration"
    fi

    echo "Bazarr configuration complete"
else
    echo "Config file not found at $CONFIG_FILE"
fi