from flask import Flask, render_template, request, jsonify
import http.client
import json
import re
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your RapidAPI configuration
RAPIDAPI_KEY = "b4204bb183mshbb02c6962ce881cp12a248jsn8a474bf78237"
RAPIDAPI_HOST = "social-download-all-in-one.p.rapidapi.com"

def get_quality_mapping(medias):
    """Map available qualities to standard 380p, 720p, 1080p"""
    quality_map = {
        '380p': None,
        '720p': None, 
        '1080p': None
    }
    
    for media in medias:
        if media['type'] != 'video':
            continue
            
        quality = media.get('quality', '').lower()
        
        # Map different quality names to standard resolutions
        if any(x in quality for x in ['hd_no_watermark', '1080', 'high']):
            if not quality_map['1080p']:
                quality_map['1080p'] = media
        elif any(x in quality for x in ['720', 'medium', 'no_watermark']):
            if not quality_map['720p']:
                quality_map['720p'] = media
        elif any(x in quality for x in ['380', '480', 'low', 'watermark']):
            if not quality_map['380p']:
                quality_map['380p'] = media
        else:
            # Fallback - assign to empty slot
            for res in ['380p', '720p', '1080p']:
                if not quality_map[res]:
                    quality_map[res] = media
                    break
    
    return {k: v for k, v in quality_map.items() if v is not None}

def format_file_size(bytes_size):
    """Convert bytes to human readable format"""
    if bytes_size == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while bytes_size >= 1024 and i < len(size_names) - 1:
        bytes_size /= 1024.0
        i += 1
    
    return f"{bytes_size:.1f} {size_names[i]}"

def validate_url(url):
    """Basic URL validation"""
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None

def get_platform_from_url(url):
    """Detect platform from URL"""
    url_lower = url.lower()
    
    if 'instagram.com' in url_lower:
        return 'instagram'
    elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
        return 'facebook'
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    else:
        return 'unknown'

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_media():
    """Process download request"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({
                'error': True,
                'message': 'URL is required'
            }), 400
        
        url = data['url'].strip()
        
        # Validate URL
        if not validate_url(url):
            return jsonify({
                'error': True,
                'message': 'Invalid URL format'
            }), 400
        
        # Detect platform
        platform = get_platform_from_url(url)
        logger.info(f"Processing {platform} URL: {url}")
        
        # Prepare API request
        conn = http.client.HTTPSConnection(RAPIDAPI_HOST)
        
        payload = json.dumps({"url": url})
        
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': RAPIDAPI_HOST,
            'Content-Type': "application/json"
        }
        
        # Make API request
        conn.request("POST", "/v1/social/autolink", payload, headers)
        response = conn.getresponse()
        response_data = response.read()
        
        # Parse response
        api_result = json.loads(response_data.decode("utf-8"))
        
        if api_result.get('error', False):
            error_message = api_result.get('message', 'Failed to process the URL')
            logger.error(f"API Error: {error_message}")
            return jsonify({
                'error': True,
                'message': error_message
            }), 400
        
        # Process the result
        processed_result = process_api_result(api_result)
        
        logger.info(f"Successfully processed media: {processed_result.get('title', 'Unknown')}")
        return jsonify(processed_result)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return jsonify({
            'error': True,
            'message': 'Invalid response from API'
        }), 500
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'error': True,
            'message': 'An unexpected error occurred. Please try again.'
        }), 500

def process_api_result(api_result):
    """Process and format API result"""
    try:
        # Extract basic information
        result = {
            'url': api_result.get('url', ''),
            'source': api_result.get('source', ''),
            'title': api_result.get('title', 'No title available'),
            'author': api_result.get('author', api_result.get('unique_id', 'Unknown')),
            'thumbnail': api_result.get('thumbnail', ''),
            'duration': api_result.get('duration', 0),
            'medias': api_result.get('medias', []),
            'type': api_result.get('type', 'single'),
            'error': False
        }
        
        # Process medias for better organization
        if result['medias']:
            # Separate video and audio
            video_medias = [m for m in result['medias'] if m.get('type') == 'video']
            audio_medias = [m for m in result['medias'] if m.get('type') == 'audio']
            
            # Add file size formatting
            for media in result['medias']:
                if 'data_size' in media:
                    media['formatted_size'] = format_file_size(media['data_size'])
            
            # Add quality mapping for frontend
            if len(video_medias) > 1:
                result['quality_map'] = get_quality_mapping(video_medias)
            
            result['has_multiple_qualities'] = len(video_medias) > 1
            result['has_audio'] = len(audio_medias) > 0
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing API result: {str(e)}")
        return {
            'error': True,
            'message': 'Error processing media information'
        }

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('index.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        'error': True,
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)