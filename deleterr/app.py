"""
Deleterr Flask application
"""

import logging
import os
from datetime import datetime
from flask import Flask, request, jsonify

from config import Config
from services.sonarr_service import SonarrService
from services.radarr_service import RadarrService
from services.jellyfin_service import JellyfinService
from services.webhook_processor import WebhookProcessor
from utils.parsers import MediaParser

# Initialize configuration
config = Config.from_env()

# Setup logging
os.makedirs(os.path.dirname(config.log_file), exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure werkzeug logger to colorize 200 responses
from werkzeug.serving import WSGIRequestHandler

class ColoredRequestHandler(WSGIRequestHandler):
    """Custom request handler that colorizes HTTP responses"""

    def log_request(self, code='-', size='-'):
        """Log HTTP request with colorized status codes"""
        if isinstance(code, str):
            # If code is already a string, use parent's method
            super().log_request(code, size)
            return

        # Color codes for different HTTP status codes
        # Green for 2xx, Yellow for 3xx, Red for 4xx, Magenta for 5xx
        if 200 <= code < 300:
            # Green and bold
            color_code = '\033[32m\033[1m'
            reset_code = '\033[0m'
        elif 300 <= code < 400:
            # Yellow
            color_code = '\033[33m'
            reset_code = '\033[0m'
        elif 400 <= code < 500:
            # Red
            color_code = '\033[31m'
            reset_code = '\033[0m'
        elif 500 <= code < 600:
            # Magenta and bold (werkzeug default for 5xx)
            color_code = '\033[35m\033[1m'
            reset_code = '\033[0m'
        else:
            color_code = ''
            reset_code = ''

        # Log with colored status code
        self.log('info', '"%s" %s%s%s %s', self.requestline, color_code, code, reset_code, size)

# Initialize services
try:
    config.validate()
    sonarr_service = SonarrService(config.sonarr_url, config.sonarr_api_key)
    radarr_service = RadarrService(config.radarr_url, config.radarr_api_key)

    # Initialize Jellyfin service if configured (optional - for enhanced series lookup)
    jellyfin_service = None
    if config.jellyfin_url and config.jellyfin_api_key:
        jellyfin_service = JellyfinService(config.jellyfin_url, config.jellyfin_api_key)
        logger.info("Jellyfin API integration enabled for enhanced series lookup")
    else:
        logger.info("Jellyfin API integration disabled (no API key configured)")

    webhook_processor = WebhookProcessor(sonarr_service, radarr_service, jellyfin_service)
    logger.info("Deleterr services initialized successfully")
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    exit(1)
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    exit(1)


@app.route('/delete', methods=['POST'])
def handle_deletion():
    """Handle Jellyfin webhook for item removal"""
    try:
        data = request.json
        if not data:
            logger.warning("Received empty webhook data")
            return jsonify({'status': 'error', 'message': 'Empty data'}), 400

        # Extract detailed information for logging
        item_type = data.get('ItemType', 'Unknown')
        item_name = data.get('Name', 'Unknown')
        series_name = data.get('SeriesName', '')
        season_num = data.get('SeasonNumber', '')
        episode_num = data.get('EpisodeNumber', '')

        # Build detailed log message
        if item_type.lower() == 'episode' and series_name and season_num and episode_num:
            detail = f"Episode: {series_name} S{season_num}E{episode_num} - {item_name}"
        elif item_type.lower() == 'season' and series_name and season_num:
            detail = f"Season: {series_name} Season {season_num}"
        elif item_type.lower() == 'series':
            detail = f"TV Show: {item_name}"
        elif item_type.lower() == 'movie':
            year = data.get('Year', '')
            detail = f"Movie: {item_name}" + (f" ({year})" if year else "")
        else:
            detail = f"{item_type}: {item_name}"

        logger.info(f"Received deletion webhook: {data.get('NotificationType', 'Unknown')} - {detail}")

        # Only process item removal events
        notification_type = data.get('NotificationType')
        if notification_type not in ['ItemDeleted', 'ItemRemoved', 'Item Deleted', 'Item Removed']:
            logger.warning(f"Ignoring non-removal webhook - NotificationType: {notification_type}")
            return jsonify({'status': 'ignored', 'message': f'Not an item removal event (got: {notification_type})'})

        # Process the removal
        success = webhook_processor.process_removal(data)

        if success:
            logger.info(f"✓ Successfully processed removal for: {detail}")
            return jsonify({
                'status': 'success',
                'message': f'Successfully unmonitored: {item_name}'
            })
        else:
            logger.error(f"✗ Failed to process removal for: {detail}")
            return jsonify({
                'status': 'error',
                'message': f'Failed to unmonitor: {item_name}'
            }), 500

    except Exception as e:
        logger.error(f"Error processing deletion webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        connections = webhook_processor.test_connections()
        services = {
            'sonarr': {
                'url': config.sonarr_url,
                'connected': connections['sonarr']
            },
            'radarr': {
                'url': config.radarr_url,
                'connected': connections['radarr']
            }
        }
        if 'jellyfin' in connections:
            services['jellyfin'] = {
                'url': config.jellyfin_url,
                'connected': connections['jellyfin']
            }
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': services
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500


@app.route('/test', methods=['POST'])
def test_webhook():
    """Test endpoint for webhook format debugging"""
    try:
        # Log raw request data for debugging
        logger.info(f"Test webhook headers: {dict(request.headers)}")
        logger.info(f"Test webhook raw data: {request.get_data(as_text=True)}")
        
        data = request.json
        logger.info(f"Test webhook parsed JSON: {data}")
        
        # Test parsing the webhook data with our parser
        parsed_item = MediaParser.parse_webhook_data(data)
        logger.info(f"Parser result: {parsed_item}")
        
        return jsonify({
            'status': 'received',
            'timestamp': datetime.now().isoformat(),
            'data': data,
            'parser_test': {
                'success': parsed_item is not None,
                'parsed_item': str(parsed_item) if parsed_item else None
            }
        })
    except Exception as e:
        logger.error(f"Test webhook error: {e}")
        logger.error(f"Raw request data: {request.get_data(as_text=True)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with basic info"""
    return jsonify({
        'name': 'Deleterr',
        'version': '0.1.0',
        'description': 'Jellyfin webhook receiver to unmonitor deleted content in Sonarr/Radarr',
        'endpoints': {
            'delete': '/delete (POST)',
            'health': '/health (GET)',
            'test': '/test (POST)'
        }
    })


if __name__ == '__main__':
    logger.info(f"Starting Deleterr on {config.host}:{config.port}")
    logger.info(f"Sonarr URL: {config.sonarr_url}")
    logger.info(f"Radarr URL: {config.radarr_url}")
    if config.jellyfin_url and config.jellyfin_api_key:
        logger.info(f"Jellyfin URL: {config.jellyfin_url}")

    app.run(
        host=config.host,
        port=config.port,
        debug=config.debug,
        request_handler=ColoredRequestHandler
    )
