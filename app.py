# --- START OF FILE app.py ---

import os
import io
import zipfile
import json 
from datetime import datetime
from flask import Flask, render_template, jsonify, send_file, request

# Import utility functions and blueprints
from utils.config_loader import load_config_file
from utils.logger import clear_logs, setup_logging
from utils import credentials_manager
from utils import encryption
from utils import settings_manager
from vendors.vonage.routes import vonage_bp
# --- START: MODIFICATION ---
from routes.notifications import notifications_bp
# --- END: MODIFICATION ---

app = Flask(__name__)

# Configuration file paths
IP_CONFIG_FILE = os.path.join('config', 'ips.json')
URI_CONFIG_FILE = os.path.join('config', 'uris.json')
NPA_DATA_CONFIG_FILE = os.path.join('config', 'npa_data.json') 

# Register Blueprints
app.register_blueprint(vonage_bp)
# --- START: MODIFICATION ---
app.register_blueprint(notifications_bp)
# --- END: MODIFICATION ---


# --- Base Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

# ... (other base routes are unchanged) ...
@app.route('/api/ips', methods=['GET'])
def get_stored_ips():
    ips = load_config_file(IP_CONFIG_FILE)
    return jsonify(ips)

@app.route('/api/uris', methods=['GET'])
def get_stored_uris():
    uris = load_config_file(URI_CONFIG_FILE)
    return jsonify(uris)

@app.route('/api/npa-data', methods=['GET'])
def get_npa_data():
    npa_data = load_config_file(NPA_DATA_CONFIG_FILE)
    return jsonify(npa_data)

# --- Settings API Endpoints ---
@app.route('/api/settings', methods=['GET'])
def get_app_settings():
    try:
        settings = settings_manager.get_all_settings()
        return jsonify(settings), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load settings: {str(e)}"}), 500

@app.route('/api/settings', methods=['POST'])
def save_app_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400
    try:
        settings_manager.save_settings(data)
        return jsonify({"message": "Settings saved successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to save settings: {str(e)}"}), 500


# --- Credential Management Routes ---
@app.route('/api/credentials/names', methods=['GET'])
def get_credential_names():
    try:
        names = credentials_manager.get_credential_names()
        all_creds = credentials_manager.get_all_credentials()
        creds_with_details = [
            {
                "name": name,
                "api_key": all_creds[name].get('api_key', ''),
                "api_key_hint": all_creds[name].get('api_key_hint', ''),
                "default_voice_callback_type": all_creds[name].get('default_voice_callback_type', ''),
                "default_voice_callback_value": all_creds[name].get('default_voice_callback_value', '')
            } for name in names
        ]
        return jsonify(creds_with_details), 200
    except Exception as e:
        return jsonify({"error": f"Failed to load credential names: {str(e)}"}), 500

@app.route('/api/credentials/verify', methods=['POST'])
def verify_master_key():
    data = request.get_json()
    master_key = data.get('master_key')
    if not master_key:
        return jsonify({"error": "Master key is required"}), 400
    try:
        encryption.get_key_from_master(master_key)
        return jsonify({"message": "Master key format is valid."}), 200
    except ValueError as e: return jsonify({"error": str(e)}), 400
    except Exception as e: return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/credentials/save', methods=['POST'])
def save_credential():
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    name = data.get('name')
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    master_key = data.get('master_key')
    voice_callback_type = data.get('voice_callback_type', '')
    voice_callback_value = data.get('voice_callback_value', '')
    original_name = data.get('original_name', name)
    if not all([name, api_key, master_key]):
        return jsonify({"error": "Missing name, api_key, or master_key"}), 400
    try:
        credentials_manager.save_credential(
            name, api_key, api_secret, master_key, 
            voice_callback_type, voice_callback_value,
            original_name=original_name
        )
        return jsonify({"message": f"Credential '{name}' saved successfully."}), 200
    except ValueError as e: return jsonify({"error": str(e)}), 400
    except Exception as e: return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

@app.route('/api/credentials/delete', methods=['POST'])
def delete_credential():
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    name = data.get('name')
    if not name: return jsonify({"error": "Credential name is required"}), 400
    try:
        if credentials_manager.delete_credential(name):
            return jsonify({"message": f"Credential '{name}' deleted successfully."}), 200
        else:
            return jsonify({"error": f"Credential '{name}' not found."}), 404
    except Exception as e: return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

@app.route('/api/credentials/rekey', methods=['POST'])
def rekey_credentials():
    """
    Decrypts all credentials with an old master key and re-encrypts them
    with a new master key.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    old_key = data.get('old_master_key')
    new_key = data.get('new_master_key')

    if not old_key or not new_key:
        return jsonify({"error": "Both old and new master keys are required"}), 400
    
    if old_key == new_key:
        return jsonify({"error": "New master key cannot be the same as the old master key."}), 400

    try:
        results = credentials_manager.rekey_all_credentials(old_key, new_key)
        
        if results.get('failed'):
            return jsonify({
                "error": "Re-keying failed for one or more credentials. No changes were saved.",
                "details": results['failed']
            }), 400
        
        return jsonify({
            "message": "All credentials re-keyed successfully.",
            "results": results
        }), 200

    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred during re-keying: {str(e)}"}), 500

@app.route('/api/credentials/import', methods=['POST'])
def import_credentials_from_file():
    """
    Imports credentials from an uploaded encrypted JSON file.
    """
    if 'credential_file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['credential_file']
    master_key = request.form.get('master_key')

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if not master_key:
        return jsonify({"error": "Master Key is required for decryption"}), 400
    if not file or not file.filename.endswith('.json'):
        return jsonify({"error": "Invalid file type, please upload a .json file"}), 400

    try:
        content = file.read().decode('utf-8')
        encrypted_creds = json.loads(content)
    except Exception as e:
        return jsonify({"error": f"Failed to read or parse JSON file: {str(e)}"}), 400

    results = {"success": [], "failed": []}
    
    for name, data in encrypted_creds.items():
        try:
            api_key = data.get('api_key')
            encrypted_secret = data.get('encrypted_secret')

            if not api_key or not encrypted_secret:
                results['failed'].append({"name": name, "reason": "Missing api_key or encrypted_secret."})
                continue
            
            decrypted_secret = encryption.decrypt_data(encrypted_secret, master_key)
            
            credentials_manager.save_credential(
                name=name,
                api_key=api_key,
                api_secret=decrypted_secret,
                master_key=master_key,
                voice_callback_type=data.get('default_voice_callback_type', ''),
                voice_callback_value=data.get('default_voice_callback_value', '')
            )
            results['success'].append(name)
        except ValueError as e:
            results['failed'].append({"name": name, "reason": str(e)})
        except Exception as e:
            results['failed'].append({"name": name, "reason": f"An unexpected error occurred: {str(e)}"})

    return jsonify({
        "message": "Import process finished.",
        "results": results
    }), 200

# --- Log Management Routes ---
@app.route('/api/logs/download')
def download_logs():
    # ... (function unchanged) ...
    log_dir = os.path.abspath('logs')
    if not os.path.isdir(log_dir):
        return jsonify({"error": "Log directory not found."}), 404
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        log_files_found = False
        for filename in os.listdir(log_dir):
            if filename.endswith(".log"):
                file_path = os.path.join(log_dir, filename)
                zf.write(file_path, arcname=filename)
                log_files_found = True
    memory_file.seek(0)
    zip_filename = f"logs_{datetime.utcnow().strftime('%Y-%m-%d_%H%MS')}.zip"
    if not log_files_found: zip_filename = f"logs_empty_{datetime.utcnow().strftime('%Y-%m-%d')}.zip"
    return send_file(memory_file, mimetype='application/zip', as_attachment=True, download_name=zip_filename)


@app.route('/api/logs/clear', methods=['POST'])
def clear_log_file():
    # ... (function unchanged) ...
    if clear_logs():
        return jsonify({"message": "All log files cleared successfully."}), 200
    else:
        return jsonify({"error": "Failed to clear log files."}), 500


# --- Main Execution ---
if __name__ == '__main__':
    setup_logging()
    os.makedirs('config', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('utils', exist_ok=True)
    # --- START: MODIFICATION ---
    os.makedirs('routes', exist_ok=True)
    # --- END: MODIFICATION ---
    os.makedirs('vendors/vonage', exist_ok=True)
    open('utils/__init__.py', 'a').close()
    # --- START: MODIFICATION ---
    open('routes/__init__.py', 'a').close()
    # --- END: MODIFICATION ---
    open('vendors/__init__.py', 'a').close()
    open('vendors/vonage/__init__.py', 'a').close()
    app.run(host='0.0.0.0', port=5000, debug=True)

# --- END OF FILE app.py ---