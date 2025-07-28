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
from services.webhook_processor import WebhookProcessor
from utils.parsers import MediaParser

# Initialize configuration
config = Config.from_env()

# Setup logging
os.makedirs(os.path.dirname(config.log_file), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize services
try:
    config.validate()
    sonarr_service = SonarrService(config.sonarr_url, config.sonarr_api_key)
    radarr_service = RadarrService(config.radarr_url, config.radarr_api_key)
    webhook_processor = WebhookProcessor(sonarr_service, radarr_service)
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
        
        logger.info(f"Received deletion webhook: {data.get('NotificationType', 'Unknown')}")
        logger.info(f"Full webhook data: {data}")
        
        # Only process item removal events
        if data.get('NotificationType') != 'ItemDeleted':
            logger.debug("Ignoring non-removal webhook")
            return jsonify({'status': 'ignored', 'message': 'Not an item removal event'})
        
        # Process the removal
        success = webhook_processor.process_removal(data)
        
        if success:
            item_name = data.get('Name', 'Unknown')
            logger.info(f"Successfully processed removal for: {item_name}")
            return jsonify({
                'status': 'success',
                'message': f'Successfully unmonitored: {item_name}'
            })
        else:
            item_name = data.get('Name', 'Unknown')
            logger.error(f"Failed to process removal for: {item_name}")
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
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': {
                'sonarr': {
                    'url': config.sonarr_url,
                    'connected': connections['sonarr']
                },
                'radarr': {
                    'url': config.radarr_url,
                    'connected': connections['radarr']
                }
            }
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
    
    app.run(
        host=config.host,
        port=config.port,
        debug=config.debug
    )
