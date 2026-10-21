#!/usr/bin/env python3
"""
UniBot Auth Module
Authentication and authorization module for UniBot
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import hashlib
import hmac
import threading
import secrets
import logging
import logging.handlers
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple
import base64

# Module metadata
MODULE_NAME = "auth"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5001,
    "default_admin_username": "unibotadmin",
    "default_admin_password": "tellmepass",
    "session_timeout": 3600,
    "session_encryption_key": "default_change_me_key_12345",
    "registration_enabled": True,
    "storage_type": "file",
    "storage_path": "/var/lib/unibot/auth",
    "sqlite_path": "/var/lib/unibot/auth/users.db",
    "log_level": "INFO",
    "log_file": "/var/log/unibot/auth.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "min_password_length": 8,
    "require_digits": True,
    "max_login_attempts": 5,
    "lockout_duration": 300
}

# In-memory storage (for demo purposes)
users: Dict[str, Dict[str, Any]] = {}
sessions: Dict[str, Dict[str, Any]] = {}
roles: Dict[str, Dict[str, Any]] = {}
login_attempts: Dict[str, Dict[str, Any]] = {}

# Default roles
DEFAULT_ROLES = {
    "anonymous": {
        "name": "anonymous",
        "description": "Anonymous user with no persistent data",
        "permissions": []
    },
    "customer": {
        "name": "customer",
        "description": "Registered customer with full bot access",
        "permissions": [
            "auth:login",
            "menu:navigate",
            "multichat:use",
            "llm:query",
            "apps:use"
        ]
    },
    "admin": {
        "name": "admin",
        "description": "Administrator with full access",
        "permissions": [
            "auth:login",
            "auth:register",
            "auth:manage_users",
            "auth:manage_roles",
            "auth:view_logs",
            "core:manage_modules",
            "web:access_admin",
            "menu:configure",
            "llm:configure",
            "multichat:configure",
            "datastore:configure",
            "apps:manage"
        ]
    }
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
        # Simple config parser (for demo, use proper configparser in production)
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


def init_default_admin():
    """Initialize default admin user if not exists"""
    admin_exists = any(u.get("username") == CONFIG["default_admin_username"] for u in users.values())
    if not admin_exists:
        user_id = str(uuid.uuid4())
        password_hash, salt = hash_password(CONFIG["default_admin_password"])
        
        users[user_id] = {
            "user_id": user_id,
            "username": CONFIG["default_admin_username"],
            "phone": "",
            "email": "admin@unibot.local",
            "first_name": "Admin",
            "last_name": "UniBot",
            "password_hash": password_hash,
            "salt": salt,
            "roles": ["admin"],
            "status": "active",
            "chat_platforms": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "last_login": None
        }
        logger.info(f"Default admin user created: {CONFIG['default_admin_username']}")


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password with salt using SHA-256"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    salted_password = (password + salt).encode('utf-8')
    hash_obj = hashlib.sha256(salted_password)
    password_hash = hash_obj.hexdigest()
    
    return password_hash, salt


def verify_password(password: str, hash: str, salt: str) -> bool:
    """Verify password against hash"""
    new_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(new_hash, hash)


def generate_token(user_id: str, platform: str) -> str:
    """Generate authentication token"""
    timestamp = str(time.time())
    random_str = secrets.token_hex(16)
    data = f"{user_id}:{platform}:{timestamp}:{random_str}"
    signature = hmac.new(
        CONFIG["session_encryption_key"].encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{base64.urlsafe_b64encode(data.encode()).decode()}.{signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify authentication token"""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        
        data = base64.urlsafe_b64decode(parts[0]).decode()
        signature = parts[1]
        
        # Verify signature
        expected_signature = hmac.new(
            CONFIG["session_encryption_key"].encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return None
        
        # Parse data
        data_parts = data.split(':')
        if len(data_parts) < 3:
            return None
        
        user_id = data_parts[0]
        platform = data_parts[1]
        timestamp = float(data_parts[2])
        
        # Check expiration
        if time.time() - timestamp > CONFIG["session_timeout"]:
            return None
        
        # Get user
        user = users.get(user_id)
        if not user:
            return None
        
        return {
            "user_id": user_id,
            "username": user.get("username", ""),
            "roles": user.get("roles", []),
            "platform": platform,
            "expires_at": timestamp + CONFIG["session_timeout"]
        }
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return None


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password against policies"""
    if len(password) < CONFIG["min_password_length"]:
        return False, f"Password must be at least {CONFIG['min_password_length']} characters"
    
    if CONFIG["require_digits"] and not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    
    return True, "OK"


def check_login_attempts(user_id: str) -> Tuple[bool, str]:
    """Check if user is locked out due to too many failed attempts"""
    attempt_info = login_attempts.get(user_id)
    if attempt_info:
        if attempt_info["count"] >= CONFIG["max_login_attempts"]:
            if time.time() - attempt_info["first_attempt"] < CONFIG["lockout_duration"]:
                remaining = int(CONFIG["lockout_duration"] - (time.time() - attempt_info["first_attempt"]))
                return False, f"Account locked. Try again in {remaining} seconds"
    return True, "OK"


def record_login_attempt(user_id: str, success: bool):
    """Record login attempt"""
    now = time.time()
    
    if user_id not in login_attempts:
        login_attempts[user_id] = {
            "count": 0,
            "first_attempt": now,
            "last_attempt": now
        }
    
    if success:
        # Reset on successful login
        del login_attempts[user_id]
    else:
        login_attempts[user_id]["count"] += 1
        login_attempts[user_id]["last_attempt"] = now


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Find user by username"""
    for user in users.values():
        if user.get("username") == username:
            return user
    return None


def get_user_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Find user by phone"""
    for user in users.values():
        if user.get("phone") == phone:
            return user
    return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find user by email"""
    for user in users.values():
        if user.get("email") == email:
            return user
    return None


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for auth module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def get_token_from_header(self) -> Optional[str]:
        """Extract token from Authorization header"""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None
    
    def get_token_from_cookie(self) -> Optional[str]:
        """Extract session token from cookie"""
        cookie_header = self.headers.get("Cookie", "")
        for part in cookie_header.split(';'):
            part = part.strip()
            if part.startswith("session_id="):
                return part[11:]
            elif part.startswith("token="):
                return part[6:]
        return None
    
    def verify_auth(self) -> Optional[Dict[str, Any]]:
        """Verify authentication for request"""
        # Try header first
        token = self.get_token_from_header()
        if not token:
            # Try cookie
            token = self.get_token_from_cookie()
        
        if token:
            return verify_token(token)
        return None
    
    def require_auth(self, required_roles: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Require authentication, optionally with specific roles"""
        user_info = self.verify_auth()
        
        if not user_info:
            self.send_error(401, "Unauthorized - Authentication required")
            return None
        
        # Check roles if specified
        if required_roles:
            user_roles = user_info.get("roles", [])
            if not any(role in user_roles for role in required_roles):
                self.send_error(403, "Forbidden - Insufficient permissions")
                return None
        
        return user_info
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            # Health check
            if path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "users": len(users),
                    "sessions": len(sessions),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
                return
            
            # Public endpoints
            if path == "/api/v1/auth/roles":
                # Get roles list
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "roles": list(DEFAULT_ROLES.values()),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path.startswith("/api/v1/auth/users/"):
                # Get user details (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                parts = path.split("/")
                if len(parts) >= 5:
                    user_id = parts[4]
                    user = users.get(user_id)
                    if user:
                        # Hide sensitive data
                        user_copy = dict(user)
                        if "password_hash" in user_copy:
                            del user_copy["password_hash"]
                        if "salt" in user_copy:
                            del user_copy["salt"]
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(user_copy, indent=2).encode())
                    else:
                        self.send_error(404, f"User {user_id} not found")
            
            elif path == "/api/v1/auth/users":
                # Get user list (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                page = int(params.get("page", ["1"])[0])
                limit = int(params.get("limit", ["100"])[0])
                role_filter = params.get("role", [None])[0]
                
                # Filter users
                filtered_users = list(users.values())
                if role_filter:
                    filtered_users = [u for u in filtered_users if role_filter in u.get("roles", [])]
                
                # Pagination
                start = (page - 1) * limit
                end = start + limit
                paginated_users = filtered_users[start:end]
                
                # Hide sensitive data
                clean_users = []
                for user in paginated_users:
                    user_copy = dict(user)
                    if "password_hash" in user_copy:
                        del user_copy["password_hash"]
                    if "salt" in user_copy:
                        del user_copy["salt"]
                    clean_users.append(user_copy)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "users": clean_users,
                    "total": len(filtered_users),
                    "page": page,
                    "limit": limit
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path == "/api/v1/auth/session":
                # Check session
                user_info = self.verify_auth()
                if user_info:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(user_info, indent=2).encode())
                else:
                    self.send_error(401, "Invalid or expired session")
            
            elif path == "/api/v1/auth/web/session":
                # Web session check
                user_info = self.require_auth()
                if user_info:
                    user = users.get(user_info["user_id"])
                    if user:
                        user_copy = dict(user)
                        if "password_hash" in user_copy:
                            del user_copy["password_hash"]
                        if "salt" in user_copy:
                            del user_copy["salt"]
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "valid",
                            "user": user_copy
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                else:
                    self.send_error(401, "Invalid session")
            
            elif path == "/api/v1/auth/permissions":
                # Get user permissions
                user_info = self.require_auth()
                if user_info:
                    user_id = user_info["user_id"]
                    user = users.get(user_id)
                    if user:
                        permissions = []
                        for role_name in user.get("roles", []):
                            role = DEFAULT_ROLES.get(role_name)
                            if role:
                                permissions.extend(role.get("permissions", []))
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "permissions": list(set(permissions))  # Remove duplicates
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                else:
                    return
            
            elif path == "/api/v1/auth/menu":
                # Get menu items for user
                user_info = self.require_auth()
                if user_info:
                    roles = user_info.get("roles", [])
                    
                    # Menu items for auth module
                    menu_items = [
                        {
                            "type": "command",
                            "label": "Зарегистрироваться",
                            "command": "/register",
                            "visible_for_roles": ["anonymous"],
                            "platform": "all"
                        }
                    ]
                    
                    # Admin menu items
                    if "admin" in roles:
                        menu_items.extend([
                            {
                                "type": "command",
                                "label": "Управлять",
                                "command": "/admin",
                                "visible_for_roles": ["admin"],
                                "platform": "all"
                            },
                            {
                                "type": "command",
                                "label": "Список пользователей",
                                "command": "/users",
                                "visible_for_roles": ["admin"],
                                "platform": "all"
                            }
                        ])
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "items": menu_items
                    }
                    self.wfile.write(json.dumps(response, indent=2).encode())
            
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
            
            if post_data:
                try:
                    data = json.loads(post_data.decode())
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
            
            # Public endpoints
            if path == "/api/v1/auth/login":
                username = data.get("username", "")
                password = data.get("password", "")
                platform = data.get("platform", "web")
                
                # Find user
                user = get_user_by_username(username)
                if not user:
                    record_login_attempt("unknown", False)
                    self.send_error(401, "Invalid username or password")
                    return
                
                # Check if locked
                can_login, message = check_login_attempts(user["user_id"])
                if not can_login:
                    self.send_error(403, message)
                    return
                
                # Verify password
                if not verify_password(password, user["password_hash"], user["salt"]):
                    record_login_attempt(user["user_id"], False)
                    self.send_error(401, "Invalid username or password")
                    return
                
                # Check status
                if user.get("status") != "active":
                    self.send_error(403, f"Account is {user.get('status')}")
                    return
                
                # Successful login
                record_login_attempt(user["user_id"], True)
                
                # Update last login
                user["last_login"] = datetime.utcnow().isoformat() + "Z"
                
                # Generate token
                token = generate_token(user["user_id"], platform)
                
                # Create session
                session_id = str(uuid.uuid4())
                sessions[session_id] = {
                    "session_id": session_id,
                    "user_id": user["user_id"],
                    "token": token,
                    "expires_at": time.time() + CONFIG["session_timeout"],
                    "created_at": time.time(),
                    "platform": platform,
                    "ip_address": self.address_string().split(':')[0]
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "token": token,
                    "session_id": session_id,
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "roles": user.get("roles", []),
                    "expires_in": CONFIG["session_timeout"]
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path == "/api/v1/auth/web/login":
                # Web login with session cookie
                username = data.get("username", "")
                password = data.get("password", "")
                
                # Find user
                user = get_user_by_username(username)
                if not user:
                    self.send_error(401, "Invalid username or password")
                    return
                
                # Verify password
                if not verify_password(password, user["password_hash"], user["salt"]):
                    self.send_error(401, "Invalid username or password")
                    return
                
                # Check status
                if user.get("status") != "active":
                    self.send_error(403, f"Account is {user.get('status')}")
                    return
                
                # Generate token
                token = generate_token(user["user_id"], "web")
                session_id = str(uuid.uuid4())
                
                # Create session
                sessions[session_id] = {
                    "session_id": session_id,
                    "user_id": user["user_id"],
                    "token": token,
                    "expires_at": time.time() + CONFIG["session_timeout"],
                    "created_at": time.time(),
                    "platform": "web"
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly")
                self.send_header("Set-Cookie", f"token={token}; Path=/; HttpOnly")
                self.end_headers()
                
                user_copy = dict(user)
                if "password_hash" in user_copy:
                    del user_copy["password_hash"]
                if "salt" in user_copy:
                    del user_copy["salt"]
                
                response = {
                    "status": "success",
                    "session_id": session_id,
                    "user": user_copy
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path == "/api/v1/auth/register":
                # User registration
                if not CONFIG["registration_enabled"]:
                    self.send_error(403, "Registration is disabled")
                    return
                
                required_fields = ["phone", "password"]
                if not all(f in data for f in required_fields):
                    self.send_error(400, "Missing required fields")
                    return
                
                phone = data.get("phone", "")
                password = data.get("password", "")
                email = data.get("email", "")
                first_name = data.get("first_name", "")
                last_name = data.get("last_name", "")
                platform = data.get("platform", "web")
                
                # Validate password
                is_valid, message = validate_password(password)
                if not is_valid:
                    self.send_error(400, message)
                    return
                
                # Check if phone/email already exists
                if get_user_by_phone(phone):
                    self.send_error(409, "Phone number already registered")
                    return
                
                if email and get_user_by_email(email):
                    self.send_error(409, "Email already registered")
                    return
                
                # Create user
                user_id = str(uuid.uuid4())
                password_hash, salt = hash_password(password)
                
                users[user_id] = {
                    "user_id": user_id,
                    "username": phone,  # Use phone as username for now
                    "phone": phone,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "password_hash": password_hash,
                    "salt": salt,
                    "roles": ["customer"],
                    "status": "active",
                    "chat_platforms": [],
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "last_login": None
                }
                
                logger.info(f"New user registered: {phone}")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "user_id": user_id,
                    "message": "Registration successful. Please login."
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path == "/api/v1/auth/logout":
                # Logout
                token = self.get_token_from_header() or self.get_token_from_cookie()
                if token:
                    # Remove session
                    for session_id, session in list(sessions.items()):
                        if session.get("token") == token:
                            del sessions[session_id]
                            break
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "session_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
                self.send_header("Set-Cookie", "token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
                self.end_headers()
                response = {
                    "status": "success",
                    "message": "Logged out successfully"
                }
                self.wfile.write(json.dumps(response).encode())
            
            elif path == "/api/v1/auth/check-permission":
                # Check permission
                user_info = self.require_auth()
                if not user_info:
                    return
                
                permission = data.get("permission", "")
                resource = data.get("resource", "")
                
                user = users.get(user_info["user_id"])
                if user:
                    permissions = []
                    for role_name in user.get("roles", []):
                        role = DEFAULT_ROLES.get(role_name)
                        if role:
                            permissions.extend(role.get("permissions", []))
                    
                    allowed = permission in permissions
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "allowed": allowed,
                        "permission": permission,
                        "resource": resource
                    }
                    self.wfile.write(json.dumps(response).encode())
            
            elif path == "/api/v1/auth/menu/register":
                # Register menu items (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                # For now, just log this
                logger.info(f"Menu registration requested by {user_info['username']}")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "message": "Menu items registration noted"
                }
                self.wfile.write(json.dumps(response).encode())
            
            # Admin endpoints
            elif path.startswith("/api/v1/auth/users/"):
                # Update or delete user (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                parts = path.split("/")
                if len(parts) >= 5:
                    user_id = parts[4]
                    
                    if self.command == "POST":
                        # Update user
                        user = users.get(user_id)
                        if user:
                            # Update fields
                            if "username" in data:
                                user["username"] = data["username"]
                            if "phone" in data:
                                user["phone"] = data["phone"]
                            if "email" in data:
                                user["email"] = data["email"]
                            if "first_name" in data:
                                user["first_name"] = data["first_name"]
                            if "last_name" in data:
                                user["last_name"] = data["last_name"]
                            if "roles" in data:
                                user["roles"] = data["roles"]
                            if "status" in data:
                                user["status"] = data["status"]
                            
                            user["updated_at"] = datetime.utcnow().isoformat() + "Z"
                            
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "success",
                                "message": f"User {user_id} updated"
                            }
                            self.wfile.write(json.dumps(response).encode())
                    elif self.command == "DELETE":
                        # Delete user
                        if user_id in users:
                            del users[user_id]
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "success",
                                "message": f"User {user_id} deleted"
                            }
                            self.wfile.write(json.dumps(response).encode())
            
            elif path == "/api/v1/auth/roles":
                # Create role (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                # For demo, just return existing roles
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "roles": list(DEFAULT_ROLES.values())
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path.startswith("/api/v1/auth/users/"):
                # Assign roles to user (admin only)
                user_info = self.require_auth(required_roles=["admin"])
                if not user_info:
                    return
                
                parts = path.split("/")
                if len(parts) >= 6 and parts[5] == "roles":
                    user_id = parts[4]
                    user = users.get(user_id)
                    if user:
                        if "roles" in data:
                            user["roles"] = data["roles"]
                            user["updated_at"] = datetime.utcnow().isoformat() + "Z"
                            
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "success",
                                "message": f"Roles updated for user {user_id}"
                            }
                            self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}")
            self.send_error(500, str(e))


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot Auth Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Load configuration
    load_config()
    
    # Initialize default admin
    init_default_admin()
    
    logger.info(f"Starting UniBot Auth Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    logger.info(f"Default admin: {CONFIG['default_admin_username']}")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start HTTP server
    server_address = (CONFIG["listen_address"], CONFIG["listen_port"])
    httpd = HTTPServer(server_address, HTTPHandler)
    
    logger.info(f"HTTP server started on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        logger.info("Auth module stopped")


if __name__ == "__main__":
    main()
