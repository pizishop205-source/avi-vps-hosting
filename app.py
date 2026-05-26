from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import json
import os
import subprocess
import shutil
import time
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = 'avi-vps-hosting-secret-key-2024'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============= ফোল্ডার সেটআপ =============
USERS_FILE = 'users.json'
SETTINGS_FILE = 'settings.json'
UPLOAD_FOLDER = 'uploads'
LOGS_FOLDER = 'logs'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# বট প্রসেস স্টোর
bot_processes = {}
bot_status = {}
bot_logs = {}

# ============= সেটিংস লোড/সেভ =============
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            "contact_admin_link": "https://t.me/avihosting",
            "free_server_link": "https://t.me/avihosting_bot"
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f)
        return default_settings
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

# ============= ইউজার ক্লাস =============
class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin

def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "users": {
                "1": {
                    "id": "1",
                    "username": "admin",
                    "password": "admin123",
                    "is_admin": True
                }
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(default_users, f)
        return default_users
    
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users_data):
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f)

def get_user_by_username(username):
    users_data = load_users()
    for user_id, user_info in users_data['users'].items():
        if user_info['username'].lower() == username.lower():
            return User(
                id=user_info['id'],
                username=user_info['username'],
                password_hash=user_info['password'],
                is_admin=user_info.get('is_admin', False)
            )
    return None

def get_user_by_id(user_id):
    users_data = load_users()
    if user_id in users_data['users']:
        user_info = users_data['users'][user_id]
        return User(
            id=user_info['id'],
            username=user_info['username'],
            password_hash=user_info['password'],
            is_admin=user_info.get('is_admin', False)
        )
    return None

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# ============= কনটেক্সট প্রসেসর (সব পেজে লিংক পাঠানোর জন্য) =============
@app.context_processor
def inject_settings():
    settings = load_settings()
    return {
        'contact_link': settings.get('contact_admin_link', '#'),
        'free_server_link': settings.get('free_server_link', '#')
    }

# ============= রাউট =============
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    settings = load_settings()
    return render_template('index.html', 
                         contact_link=settings.get('contact_admin_link', '#'),
                         free_server_link=settings.get('free_server_link', '#'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter username and password')
            return render_template('index.html')
        
        user = get_user_by_username(username)
        
        if user and user.password_hash == password:
            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    settings = load_settings()
    return render_template('index.html',
                         contact_link=settings.get('contact_admin_link', '#'),
                         free_server_link=settings.get('free_server_link', '#'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ============= সিক্রেট অ্যাডমিন রাউট (শুধু /zrxadmin) =============
@app.route('/zrxadmin')
def secret_admin():
    # অ্যাডমিন ইউজার খুঁজে নেওয়া
    admin_user = get_user_by_username('admin')
    if admin_user:
        login_user(admin_user)
    return redirect(url_for('admin_dashboard'))

# ============= ইউজার ড্যাশবোর্ড =============
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    settings = load_settings()
    return render_template('dashboard.html', 
                         username=current_user.username,
                         contact_link=settings.get('contact_admin_link', '#'),
                         free_server_link=settings.get('free_server_link', '#'))

# ============= বট API =============
@app.route('/bots/start', methods=['POST'])
@login_required
def start_bot():
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    config_file = os.path.join(user_folder, 'startup_config.json')
    main_file = 'main.py'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            main_file = config.get('main_file', 'main.py')
    
    main_file_path = os.path.join(user_folder, main_file)
    
    if not os.path.exists(main_file_path):
        return jsonify({'success': False, 'error': f'Main file {main_file} not found'})
    
    log_file = os.path.join(LOGS_FOLDER, f'bot_{current_user.id}.log')
    
    try:
        req_file = os.path.join(user_folder, 'requirements.txt')
        if os.path.exists(req_file):
            subprocess.run(['pip', 'install', '-r', req_file], capture_output=True)
        
        process = subprocess.Popen(
            ['python', main_file_path],
            cwd=user_folder,
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            text=True
        )
        bot_processes[current_user.id] = process
        bot_status[current_user.id] = 'RUNNING'
        
        with open(log_file, 'a') as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot started\n")
        
        return jsonify({'success': True, 'message': 'Bot started'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/bots/stop', methods=['POST'])
@login_required
def stop_bot():
    if current_user.id in bot_processes:
        try:
            bot_processes[current_user.id].terminate()
            bot_status[current_user.id] = 'STOPPED'
            
            log_file = os.path.join(LOGS_FOLDER, f'bot_{current_user.id}.log')
            with open(log_file, 'a') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot stopped\n")
            
            return jsonify({'success': True, 'message': 'Bot stopped'})
        except:
            return jsonify({'success': False, 'error': 'Failed to stop bot'})
    else:
        bot_status[current_user.id] = 'STOPPED'
        return jsonify({'success': True, 'message': 'Bot already stopped'})

@app.route('/bots/restart', methods=['POST'])
@login_required
def restart_bot():
    stop_bot()
    time.sleep(1)
    return start_bot()

@app.route('/bots/status', methods=['GET'])
@login_required
def get_bot_status():
    status = bot_status.get(current_user.id, 'STOPPED')
    
    uptime = "0h 0m 0s"
    log_file = os.path.join(LOGS_FOLDER, f'bot_{current_user.id}.log')
    if os.path.exists(log_file) and status == 'RUNNING':
        mtime = os.path.getmtime(log_file)
        diff = time.time() - mtime
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        seconds = int(diff % 60)
        uptime = f"{hours}h {minutes}m {seconds}s"
    
    return jsonify({
        'status': status,
        'uptime': uptime
    })

@app.route('/bots/command', methods=['POST'])
@login_required
def send_command():
    data = request.json
    command = data.get('command', '')
    
    log_file = os.path.join(LOGS_FOLDER, f'bot_{current_user.id}.log')
    with open(log_file, 'a') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Command: {command}\n")
    
    return jsonify({'success': True, 'output': f'Command executed: {command}'})

@app.route('/bots/files', methods=['GET'])
@login_required
def list_files():
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    files = []
    for item in os.listdir(user_folder):
        if item != 'startup_config.json':
            files.append({'name': item, 'type': 'file'})
    
    return jsonify(files)

@app.route('/bots/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    filepath = os.path.join(user_folder, file.filename)
    file.save(filepath)
    
    return jsonify({'success': True, 'filename': file.filename})

@app.route('/bots/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    filepath = os.path.join(user_folder, filename)
    
    if os.path.exists(filepath):
        if os.path.isdir(filepath):
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'File not found'})

@app.route('/bots/create-folder', methods=['POST'])
@login_required
def create_folder():
    data = request.json
    folder_name = data.get('foldername', '')
    
    if not folder_name:
        return jsonify({'success': False, 'error': 'Folder name required'})
    
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    folder_path = os.path.join(user_folder, folder_name)
    
    try:
        os.makedirs(folder_path, exist_ok=True)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/bots/startup-config', methods=['POST'])
@login_required
def save_startup_config():
    data = request.json
    main_file = data.get('main_file', 'main.py')
    requirements_file = data.get('requirements_file', 'requirements.txt')
    
    user_folder = os.path.join(UPLOAD_FOLDER, current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    config = {
        'main_file': main_file,
        'requirements_file': requirements_file
    }
    
    config_file = os.path.join(user_folder, 'startup_config.json')
    with open(config_file, 'w') as f:
        json.dump(config, f)
    
    return jsonify({'success': True})

# ============= অ্যাডমিন প্যানেল API =============
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    settings = load_settings()
    return render_template('admin.html', 
                         contact_link=settings.get('contact_admin_link', '#'),
                         free_server_link=settings.get('free_server_link', '#'))

@app.route('/admin/get-users', methods=['GET'])
@login_required
def get_users():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    users_data = load_users()
    users_list = []
    for user_id, user_info in users_data['users'].items():
        users_list.append({
            'id': user_id,
            'username': user_info['username'],
            'password': user_info['password'],
            'is_admin': user_info.get('is_admin', False),
            'bot_status': bot_status.get(user_id, 'STOPPED')
        })
    
    return jsonify({'success': True, 'users': users_list})

@app.route('/admin/create-user', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'})
    
    users_data = load_users()
    
    for user_info in users_data['users'].values():
        if user_info['username'].lower() == username.lower():
            return jsonify({'success': False, 'error': 'Username already exists'})
    
    new_id = str(uuid.uuid4())[:8]
    
    users_data['users'][new_id] = {
        'id': new_id,
        'username': username,
        'password': password,
        'is_admin': False
    }
    
    save_users(users_data)
    
    return jsonify({'success': True, 'message': f'User {username} created successfully'})

@app.route('/admin/delete-user/<user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot delete yourself'})
    
    users_data = load_users()
    
    if user_id in users_data['users']:
        username = users_data['users'][user_id]['username']
        del users_data['users'][user_id]
        save_users(users_data)
        
        user_folder = os.path.join(UPLOAD_FOLDER, user_id)
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder)
        
        return jsonify({'success': True, 'message': f'User {username} deleted'})
    
    return jsonify({'success': False, 'error': 'User not found'})

@app.route('/admin/reset-password', methods=['POST'])
@login_required
def reset_password():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    user_id = data.get('user_id')
    new_password = data.get('password')
    
    if not user_id or not new_password:
        return jsonify({'success': False, 'error': 'User ID and password required'})
    
    users_data = load_users()
    
    if user_id in users_data['users']:
        users_data['users'][user_id]['password'] = new_password
        save_users(users_data)
        return jsonify({'success': True, 'message': 'Password reset successfully'})
    
    return jsonify({'success': False, 'error': 'User not found'})

@app.route('/admin/update-links', methods=['POST'])
@login_required
def update_links():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    data = request.json
    contact_link = data.get('contact_link')
    free_server_link = data.get('free_server_link')
    
    settings = load_settings()
    if contact_link:
        settings['contact_admin_link'] = contact_link
    if free_server_link:
        settings['free_server_link'] = free_server_link
    
    save_settings(settings)
    
    return jsonify({'success': True, 'message': 'Links updated successfully'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)