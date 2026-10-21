#!/usr/bin/env python3
"""
UniBot Web Module
Web administration console for UniBot
Version: 2026.10.21_2
"""

import os
import sys
import json
import uuid
import time
import threading
import logging
import logging.handlers
from datetime import datetime, timedelta

# Imports for the built-in HTTP server fallback.
# These are required unconditionally: the fallback HTTPHandler class is defined
# at module level, so it must be importable even when Flask is available.
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Try to import Flask, if not available use built-in HTTP server
FLASK_IMPORT_ERROR = None
try:
    from flask import Flask, request, jsonify, render_template, redirect, url_for, session, make_response
    from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
    from werkzeug.security import generate_password_hash, check_password_hash
    USE_FLASK = True
except ImportError as exc:
    USE_FLASK = False
    FLASK_IMPORT_ERROR = exc

# Module metadata
MODULE_NAME = "web"
MODULE_VERSION = "2026.10.21_2"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 8080,
    "use_https": False,
    "ssl_cert": "/etc/ssl/certs/web.crt",
    "ssl_key": "/etc/ssl/private/web.key",
    "title": "UniBot Administration Console",
    "owner_name": "UniBot Team",
    "owner_email": "admin@unibot.local",
    "admin_path": "/admin",
    "theme": "default",
    "session_timeout": 3600,
    "secret_key": "default_change_me_secret_key_12345",
    "log_level": "INFO",
    "log_file": "/var/log/unibot/web.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "static_dir": "/var/www/unibot/static",
    "templates_dir": "/var/www/unibot/templates",
    "core_endpoint": "http://core:5000",
    "auth_endpoint": "http://auth:5001"
}

# Logging setup
def setup_logging():
    """Setup logging configuration"""
    log_dir = os.path.dirname(CONFIG["log_file"])
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(MODULE_NAME)
    logger.setLevel(getattr(logging, CONFIG["log_level"].upper(), logging.INFO))
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        CONFIG["log_file"],
        maxBytes=CONFIG["log_max_size"],
        backupCount=CONFIG["log_backup_count"]
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()


def load_config():
    """Load configuration from module.conf"""
    conf_path = os.path.join(os.path.dirname(__file__), "module.conf")
    if os.path.exists(conf_path):
        with open(conf_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Handle different types
                    if value.isdigit():
                        value = int(value)
                    elif value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    # Update config
                    CONFIG[key] = value


def call_core_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Call core module API"""
    import requests
    url = f"{CONFIG['core_endpoint']}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        elif method == "PUT":
            response = requests.put(url, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            return {"status": "error", "message": "Unsupported method"}
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": f"Core API error: {response.status_code}", "details": response.text}
    except Exception as e:
        logger.error(f"Error calling core API {endpoint}: {e}")
        return {"status": "error", "message": str(e)}


def call_auth_api(endpoint: str, method: str = "GET", data: dict = None, headers: dict = None) -> dict:
    """Call auth module API"""
    import requests
    url = f"{CONFIG['auth_endpoint']}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=10)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            return {"status": "error", "message": "Unsupported method"}
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": f"Auth API error: {response.status_code}", "details": response.text}
    except Exception as e:
        logger.error(f"Error calling auth API {endpoint}: {e}")
        return {"status": "error", "message": str(e)}


def auth_headers() -> dict:
    """Build the Authorization header for calls to the auth module.

    The auth module requires a bearer token for the admin-only endpoints
    (users list, menu, ...), so the token stored in the session must be
    forwarded on every request.
    """
    token = session.get('user', {}).get('token')
    return {'Authorization': f'Bearer {token}'} if token else {}


# Flask Application
if USE_FLASK:
    app = Flask(__name__)
    app.secret_key = CONFIG["secret_key"]
    app.permanent_session_lifetime = timedelta(seconds=CONFIG["session_timeout"])
    
    # Configure static and template folders
    if not os.path.exists(CONFIG["static_dir"]):
        os.makedirs(CONFIG["static_dir"], exist_ok=True)
    if not os.path.exists(CONFIG["templates_dir"]):
        os.makedirs(CONFIG["templates_dir"], exist_ok=True)
    
    app.static_folder = CONFIG["static_dir"]
    app.template_folder = CONFIG["templates_dir"]
    
    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # User model
    class User(UserMixin):
        def __init__(self, user_data):
            self.user_data = user_data
        
        def get_id(self):
            return str(self.user_data.get("user_id", ""))
        
        @property
        def is_authenticated(self):
            return True
        
        @property
        def is_active(self):
            # Default to active when the upstream API reports no account status.
            return self.user_data.get("status", "active") == "active"
        
        @property
        def is_anonymous(self):
            return False
        
        def has_role(self, role):
            return role in self.user_data.get("roles", [])
        
        def get(self, key, default=None):
            """Dict-style access so templates can use user.<key> and user['<key>']."""
            return self.user_data.get(key, default)
        
        def __getitem__(self, key):
            return self.user_data[key]
        
        def __contains__(self, key):
            return key in self.user_data
        
        def __getattr__(self, name):
            # Fall back to the underlying user_data for unknown attributes.
            # Only called when normal attribute lookup fails.
            try:
                return self.__dict__["user_data"][name]
            except KeyError:
                raise AttributeError(name)
    
    @login_manager.user_loader
    def load_user(user_id):
        # In a real implementation, this would load from auth module
        # For now, we'll check the session
        if 'user' in session:
            user_data = session['user']
            if user_data.get('user_id') == user_id:
                return User(user_data)
        return None
    
    # Routes
    @app.route('/')
    def index():
        return redirect(url_for('dashboard'))
    
    @app.route('/admin')
    @app.route('/admin/')
    def admin_index():
        return redirect(url_for('dashboard'))
    
    @app.route('/admin/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            remember = request.form.get('remember', 'false').lower() == 'true'
            
            # Call auth module
            result = call_auth_api('/api/v1/auth/login', 'POST', {
                'username': username,
                'password': password,
                'platform': 'web'
            })
            
            if result.get('status') == 'success':
                # Store user in session
                user_data = {
                    'user_id': result.get('user_id'),
                    'username': result.get('username'),
                    'roles': result.get('roles', []),
                    'token': result.get('token'),
                    # The auth API only reports the request status; a successful
                    # login already implies that the account is active.
                    'status': 'active',
                    'logged_in': True
                }
                session['user'] = user_data
                session['logged_in'] = True
                if remember:
                    session.permanent = True
                
                # Register the user with Flask-Login: this sets the
                # session['_user_id'] key that @login_required relies on.
                if not login_user(User(user_data), remember=remember):
                    logger.error(f"Login rejected for {username}: user is not active")
                    session.clear()
                    return render_template('login.html',
                                           error='Account is not active',
                                           title=CONFIG['title'])

                logger.info(f"User logged in: {username}")
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html',
                                       error=result.get('message', 'Invalid credentials'),
                                       title=CONFIG['title'])
        
        return render_template('login.html', title=CONFIG['title'])
    
    @app.route('/admin/logout')
    @login_required
    def logout():
        # Call auth module logout
        token = session.get('user', {}).get('token')
        if token:
            call_auth_api('/api/v1/auth/logout', 'POST', {}, headers={'Authorization': f'Bearer {token}'})
        
        logout_user()
        session.clear()
        logger.info(f"User logged out")
        return redirect(url_for('login'))
    
    @app.route('/admin/dashboard')
    @login_required
    def dashboard():
        # Get modules list from core
        modules_result = call_core_api('/api/v1/modules')
        modules = modules_result.get('modules', [])
        
        # Get health status
        health_result = call_core_api('/api/v1/health')
        
        return render_template('dashboard.html',
                             user=current_user.user_data,
                             modules=modules,
                             health=health_result,
                             title=CONFIG['title'],
                             owner=CONFIG['owner_name'])
    
    @app.route('/admin/modules')
    @login_required
    def modules_list():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        modules_result = call_core_api('/api/v1/modules')
        modules = modules_result.get('modules', [])
        
        return render_template('modules.html',
                             user=current_user.user_data,
                             modules=modules,
                             title=f"Modules - {CONFIG['title']}")
    
    @app.route('/admin/modules/<module_name>')
    @login_required
    def module_detail(module_name):
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        # Get module status
        status_result = call_core_api(f'/api/v1/modules/{module_name}/status')
        module = status_result.get('module', status_result) if status_result.get('status') != 'error' else {}
        
        return render_template('module_detail.html',
                             user=current_user.user_data,
                             module=module,
                             module_name=module_name,
                             title=f"{module_name} - {CONFIG['title']}")
    
    @app.route('/admin/users')
    @login_required
    def users_list():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        # Get users from auth module
        result = call_auth_api('/api/v1/auth/users', 'GET', headers=auth_headers())
        users = result.get('users', [])
        
        return render_template('users.html',
                             user=current_user.user_data,
                             users=users,
                             title=f"Users - {CONFIG['title']}")
    
    @app.route('/admin/roles')
    @login_required
    def roles_list():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        # Get roles from auth module
        result = call_auth_api('/api/v1/auth/roles', 'GET', headers=auth_headers())
        roles = result.get('roles', [])
        
        return render_template('roles.html',
                             user=current_user.user_data,
                             roles=roles,
                             title=f"Roles - {CONFIG['title']}")
    
    @app.route('/admin/menu')
    @login_required
    def menu_config():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        # Get menu from auth module
        result = call_auth_api('/api/v1/auth/menu', 'GET', {}, headers=auth_headers())
        menu_items = result.get('items', [])
        
        return render_template('menu.html',
                             user=current_user.user_data,
                             menu_items=menu_items,
                             title=f"Menu Configuration - {CONFIG['title']}")
    
    @app.route('/admin/settings')
    @login_required
    def settings():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        return render_template('settings.html',
                             user=current_user.user_data,
                             config=CONFIG,
                             title=f"Settings - {CONFIG['title']}")
    
    @app.route('/admin/logs')
    @login_required
    def logs():
        if not current_user.has_role('admin'):
            return redirect(url_for('dashboard'))
        
        # Tail the module log file if it is available
        log_lines = []
        try:
            log_path = CONFIG['log_file']
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    log_lines = f.readlines()[-200:]
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
        
        return render_template('logs.html',
                             user=current_user.user_data,
                             log_lines=log_lines,
                             log_file=CONFIG['log_file'],
                             title=f"Logs - {CONFIG['title']}")
    
    # API endpoints
    @app.route('/api/v1/auth/login', methods=['POST'])
    def api_login():
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        # Call auth module
        result = call_auth_api('/api/v1/auth/login', 'POST', {
            'username': username,
            'password': password,
            'platform': 'web'
        })
        
        if result.get('status') == 'success':
            # Create session
            session['user'] = {
                'user_id': result.get('user_id'),
                'username': result.get('username'),
                'roles': result.get('roles', []),
                'token': result.get('token'),
                'status': 'active',
                'logged_in': True
            }
            session['logged_in'] = True
            
            # Register with Flask-Login so @login_required accepts the session
            login_user(User({
                'user_id': result.get('user_id'),
                'username': result.get('username'),
                'roles': result.get('roles', []),
                'token': result.get('token'),
                'status': 'active'
            }))
            
            return jsonify({
                'status': 'success',
                'message': 'Login successful',
                'user': {
                    'user_id': result.get('user_id'),
                    'username': result.get('username'),
                    'roles': result.get('roles', [])
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('message', 'Invalid credentials')
            }), 401
    
    @app.route('/api/v1/auth/status', methods=['GET'])
    @login_required
    def api_auth_status():
        return jsonify({
            'status': 'authenticated',
            'user': current_user.user_data
        })
    
    @app.route('/api/v1/auth/logout', methods=['POST'])
    @login_required
    def api_logout():
        logout_user()
        session.clear()
        return jsonify({'status': 'success', 'message': 'Logged out'})
    
    @app.route('/api/v1/modules', methods=['GET'])
    @login_required
    def api_modules():
        if not current_user.has_role('admin'):
            return jsonify({'status': 'error', 'message': 'Insufficient permissions'}), 403
        
        result = call_core_api('/api/v1/modules')
        return jsonify(result)
    
    @app.route('/api/v1/users', methods=['GET'])
    @login_required
    def api_users():
        if not current_user.has_role('admin'):
            return jsonify({'status': 'error', 'message': 'Insufficient permissions'}), 403
        
        result = call_auth_api('/api/v1/auth/users', 'GET', headers=auth_headers())
        return jsonify(result)
    
    @app.route('/api/v1/system/status', methods=['GET'])
    @login_required
    def api_system_status():
        result = call_core_api('/api/v1/health')
        return jsonify(result)
    
    # Health check endpoint
    @app.route('/api/v1/health', methods=['GET'])
    def api_health():
        response = {
            "status": "healthy",
            "service": "web",
            "version": MODULE_VERSION,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        return jsonify(response)
    
    # Static files
    @app.route('/static/<path:filename>')
    def static_files(filename):
        return app.send_static_file(filename)
    
    # Create templates directory and basic templates
    def create_templates():
        templates_dir = CONFIG["templates_dir"]
        os.makedirs(templates_dir, exist_ok=True)
        
        # Base template
        base_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ title }}{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>{{ title }}</h1>
        <nav>
            {% if user and user.get('logged_in') %}
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            {% if 'admin' in user.get('roles', []) %}
            <a href="{{ url_for('modules_list') }}">Modules</a>
            <a href="{{ url_for('users_list') }}">Users</a>
            <a href="{{ url_for('roles_list') }}">Roles</a>
            <a href="{{ url_for('menu_config') }}">Menu</a>
            <a href="{{ url_for('settings') }}">Settings</a>
            <a href="{{ url_for('logs') }}">Logs</a>
            {% endif %}
            <a href="{{ url_for('logout') }}">Logout</a>
            {% else %}
            <a href="{{ url_for('login') }}">Login</a>
            {% endif %}
        </nav>
    </header>
    <main>
        {% block content %}{% endblock %}
    </main>
    <footer>
        <p>&copy; {{ owner }} - UniBot Administration Console</p>
    </footer>
</body>
</html>'''
        
        login_template = '''{% extends "base.html" %}

{% block title %}Login - {{ title }}{% endblock %}

{% block content %}
<div class="login-container">
    <h2>Login</h2>
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST" action="{{ url_for('login') }}">
        <div class="form-group">
            <label for="username">Username:</label>
            <input type="text" id="username" name="username" required>
        </div>
        <div class="form-group">
            <label for="password">Password:</label>
            <input type="password" id="password" name="password" required>
        </div>
        <div class="form-group">
            <label>
                <input type="checkbox" name="remember" value="true"> Remember me
            </label>
        </div>
        <button type="submit">Login</button>
    </form>
</div>
{% endblock %}'''
        
        dashboard_template = '''{% extends "base.html" %}

{% block title %}Dashboard - {{ title }}{% endblock %}

{% block content %}
<h2>Welcome, {{ user.username }}!</h2>
<p>Roles: {{ ', '.join(user.roles) }}</p>

<h3>System Health</h3>
{% if health %}
<div class="health-status">
    <p>Status: <span class="status-{{ health.status }}">{{ health.status }}</span></p>
    <p>Modules: {{ health.modules|length }}</p>
    <p>Queue Size: {{ health.queue_size }}</p>
    <p>Cache Size: {{ health.cache_size }}</p>
</div>
{% endif %}

<h3>Connected Modules</h3>
<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Version</th>
        </tr>
    </thead>
    <tbody>
        {% for module in modules %}
        <tr>
            <td>{{ module.name }}</td>
            <td><span class="status-{{ module.status }}">{{ module.status }}</span></td>
            <td>{{ module.version }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        modules_template = '''{% extends "base.html" %}

{% block title %}Modules - {{ title }}{% endblock %}

{% block content %}
<h2>Connected Modules</h2>

<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Version</th>
            <th>Status</th>
            <th>Endpoints</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for module in modules %}
        <tr>
            <td>{{ module.name }}</td>
            <td>{{ module.version }}</td>
            <td><span class="status-{{ module.status }}">{{ module.status }}</span></td>
            <td>{{ module.endpoints|join(', ') }}</td>
            <td><a href="{{ url_for('module_detail', module_name=module.name) }}">View</a></td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        users_template = '''{% extends "base.html" %}

{% block title %}Users - {{ title }}{% endblock %}

{% block content %}
<h2>Users</h2>

<table>
    <thead>
        <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Roles</th>
            <th>Status</th>
            <th>Last Login</th>
        </tr>
    </thead>
    <tbody>
        {% for user in users %}
        <tr>
            <td>{{ user.username }}</td>
            <td>{{ user.email or '-' }}</td>
            <td>{{ user.phone or '-' }}</td>
            <td>{{ user.roles|join(', ') }}</td>
            <td><span class="status-{{ user.status }}">{{ user.status }}</span></td>
            <td>{{ user.last_login or 'Never' }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        module_detail_template = '''{% extends "base.html" %}

{% block title %}{{ module_name }} - {{ title }}{% endblock %}

{% block content %}
<h2>Module: {{ module_name }}</h2>

{% if module %}
<table>
    <thead>
        <tr>
            <th>Property</th>
            <th>Value</th>
        </tr>
    </thead>
    <tbody>
        <tr><td>Name</td><td>{{ module.name or '-' }}</td></tr>
        <tr><td>Version</td><td>{{ module.version or '-' }}</td></tr>
        <tr><td>Status</td><td><span class="status-{{ module.status }}">{{ module.status or 'unknown' }}</span></td></tr>
        <tr><td>Host</td><td>{{ module.host or '-' }}</td></tr>
        <tr><td>Port</td><td>{{ module.port or '-' }}</td></tr>
        <tr><td>Last Ping</td><td>{{ module.last_ping or 'Never' }}</td></tr>
        <tr><td>Registered At</td><td>{{ module.registered_at or '-' }}</td></tr>
    </tbody>
</table>

<h3>Endpoints</h3>
<ul>
    {% for endpoint in module.endpoints or [] %}
    <li>{{ endpoint }}</li>
    {% else %}
    <li>No endpoints registered</li>
    {% endfor %}
</ul>
{% else %}
<p>Module information is not available.</p>
{% endif %}
{% endblock %}'''
        
        roles_template = '''{% extends "base.html" %}

{% block title %}Roles - {{ title }}{% endblock %}

{% block content %}
<h2>Roles</h2>

<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Permissions</th>
        </tr>
    </thead>
    <tbody>
        {% for role in roles %}
        <tr>
            <td>{{ role.name }}</td>
            <td>{{ role.description or '-' }}</td>
            <td>
                {% for permission in role.permissions or [] %}
                <span class="permission">{{ permission }}</span>
                {% else %}
                -
                {% endfor %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        menu_template = '''{% extends "base.html" %}

{% block title %}Menu Configuration - {{ title }}{% endblock %}

{% block content %}
<h2>Menu Configuration</h2>

<table>
    <thead>
        <tr>
            <th>Label</th>
            <th>Type</th>
            <th>Command</th>
            <th>Platform</th>
            <th>Visible For Roles</th>
        </tr>
    </thead>
    <tbody>
        {% for item in menu_items %}
        <tr>
            <td>{{ item.label }}</td>
            <td>{{ item.type or '-' }}</td>
            <td>{{ item.command or '-' }}</td>
            <td>{{ item.platform or 'all' }}</td>
            <td>{{ item.visible_for_roles|join(', ') }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        settings_template = '''{% extends "base.html" %}

{% block title %}Settings - {{ title }}{% endblock %}

{% block content %}
<h2>Settings</h2>

<table>
    <thead>
        <tr>
            <th>Setting</th>
            <th>Value</th>
        </tr>
    </thead>
    <tbody>
        {% for key, value in config.items() %}
        <tr>
            <td>{{ key }}</td>
            <td>{{ value }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}'''
        
        logs_template = '''{% extends "base.html" %}

{% block title %}Logs - {{ title }}{% endblock %}

{% block content %}
<h2>Logs</h2>
<p>Log file: <code>{{ log_file }}</code></p>

<pre class="log-output">
{% for line in log_lines %}{{ line }}
{% else %}No log entries available.
{% endfor %}</pre>
{% endblock %}'''
        
        # Write templates
        with open(os.path.join(templates_dir, 'base.html'), 'w') as f:
            f.write(base_template)
        with open(os.path.join(templates_dir, 'login.html'), 'w') as f:
            f.write(login_template)
        with open(os.path.join(templates_dir, 'dashboard.html'), 'w') as f:
            f.write(dashboard_template)
        with open(os.path.join(templates_dir, 'modules.html'), 'w') as f:
            f.write(modules_template)
        with open(os.path.join(templates_dir, 'users.html'), 'w') as f:
            f.write(users_template)
        with open(os.path.join(templates_dir, 'module_detail.html'), 'w') as f:
            f.write(module_detail_template)
        with open(os.path.join(templates_dir, 'roles.html'), 'w') as f:
            f.write(roles_template)
        with open(os.path.join(templates_dir, 'menu.html'), 'w') as f:
            f.write(menu_template)
        with open(os.path.join(templates_dir, 'settings.html'), 'w') as f:
            f.write(settings_template)
        with open(os.path.join(templates_dir, 'logs.html'), 'w') as f:
            f.write(logs_template)
        
        # Create simple CSS
        css = '''body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 0;
    background-color: #f5f5f5;
}

header {
    background-color: #3498db;
    color: white;
    padding: 1rem;
}

header h1 {
    margin: 0;
}

header nav {
    margin-top: 1rem;
}

header nav a {
    color: white;
    margin-right: 1rem;
    text-decoration: none;
}

header nav a:hover {
    text-decoration: underline;
}

main {
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
}

footer {
    background-color: #3498db;
    color: white;
    padding: 1rem;
    text-align: center;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}

table, th, td {
    border: 1px solid #ddd;
}

th, td {
    padding: 0.5rem;
    text-align: left;
}

th {
    background-color: #3498db;
    color: white;
}

tr:nth-child(even) {
    background-color: #f2f2f2;
}

.login-container {
    max-width: 400px;
    margin: 2rem auto;
    padding: 2rem;
    background: white;
    border-radius: 5px;
    box-shadow: 0 0 10px rgba(0,0,0,0.1);
}

.form-group {
    margin: 1rem 0;
}

.form-group label {
    display: block;
    margin-bottom: 0.5rem;
}

.form-group input {
    width: 100%;
    padding: 0.5rem;
    box-sizing: border-box;
}

button {
    background-color: #3498db;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 3px;
    cursor: pointer;
}

button:hover {
    background-color: #2980b9;
}

.error {
    color: red;
    margin: 1rem 0;
}

.status-healthy {
    color: green;
}

.status-degraded {
    color: orange;
}

.status-unhealthy {
    color: red;
}

.status-active {
    color: green;
}

.status-inactive {
    color: orange;
}

.status-error {
    color: red;
}'''
        
        with open(os.path.join(CONFIG["static_dir"], 'style.css'), 'w') as f:
            f.write(css)


if USE_FLASK:
    # Create templates before running
    create_templates()
    
    def run_flask():
        logger.info(f"Starting UniBot Web Module v{MODULE_VERSION}")
        logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
        
        if CONFIG["use_https"]:
            # For HTTPS, we need SSL context
            import ssl
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            ssl_context.load_cert_chain(CONFIG["ssl_cert"], CONFIG["ssl_key"])
            app.run(
                host=CONFIG["listen_address"],
                port=CONFIG["listen_port"],
                ssl_context=ssl_context
            )
        else:
            app.run(
                host=CONFIG["listen_address"],
                port=CONFIG["listen_port"],
                threaded=True
            )


# HTTP Server (fallback if Flask not available)
class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for web module (fallback)"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            # Health check
            if path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "service": "web",
                    "version": MODULE_VERSION,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response).encode())
                return
            
            if path == "/admin" or path == "/admin/" or path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>{CONFIG['title']}</title>
                </head>
                <body>
                    <h1>{CONFIG['title']}</h1>
                    <p>UniBot Web Module is running</p>
                    <p>Flask is not available. Please install Flask for full functionality.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            
            elif path == "/admin/login":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Login - {CONFIG['title']}</title>
                </head>
                <body>
                    <h1>Login</h1>
                    <form method="POST" action="/admin/login">
                        <label>Username: <input type="text" name="username"></label><br>
                        <label>Password: <input type="password" name="password"></label><br>
                        <button type="submit">Login</button>
                    </form>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            
            elif path == "/api/v1/system/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "running",
                    "module": MODULE_NAME,
                    "version": MODULE_VERSION,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling GET {path}: {e}")
            self.send_error(500, str(e))
    
    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            
            if path == "/admin/login":
                self.send_response(302)
                self.send_header("Location", "/admin")
                self.end_headers()
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}")
            self.send_error(500, str(e))


def run_http_server():
    """Run HTTP server (fallback)"""
    logger.warning(
        "Flask is unavailable, falling back to the built-in HTTP server. "
        "The web console will not provide the full admin UI. "
        f"Underlying import error: {FLASK_IMPORT_ERROR!r}"
    )
    logger.info(f"Starting UniBot Web Module v{MODULE_VERSION} (HTTP mode)")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    
    server_address = (CONFIG["listen_address"], CONFIG["listen_port"])
    httpd = HTTPServer(server_address, HTTPHandler)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main():
    """Main entry point"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot Web Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--https", action="store_true", help="Use HTTPS")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    CONFIG["use_https"] = args.https or CONFIG["use_https"]
    
    # Load configuration
    load_config()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if USE_FLASK:
        run_flask()
    else:
        run_http_server()


if __name__ == "__main__":
    main()
