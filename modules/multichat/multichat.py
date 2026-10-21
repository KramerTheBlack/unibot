#!/usr/bin/env python3
"""
UniBot Multi-chat Module
Multi-platform chat bot module for UniBot
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import threading
import queue
import logging
import logging.handlers
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple
import re

# Module metadata
MODULE_NAME = "multichat"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5003,
    "supported_platforms": ["vk", "telegram", "max"],
    "webhook_enabled": True,
    "webhook_path": "/webhook",
    "max_message_length": 4096,
    "message_timeout": 30,
    "rate_limit": 10,
    "state_ttl": 3600,
    "log_level": "INFO",
    "log_file": "/var/log/unibot/multichat.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "core_endpoint": "http://core:5000",
    "auth_endpoint": "http://auth:5001"
}

# Global state
bots: Dict[str, Dict[str, Any]] = {}
platforms: Dict[str, Dict[str, Any]] = {}
user_states: Dict[str, Dict[str, Any]] = {}
message_queue: queue.Queue = queue.Queue()
command_handlers: Dict[str, Dict[str, Any]] = {}
rate_limits: Dict[str, Dict[str, Any]] = {}

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
            current_section = None
            for line in f:
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                elif line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if current_section:
                        full_key = f"{current_section}_{key}"
                    else:
                        full_key = key
                    
                    # Handle different types
                    if value.isdigit():
                        value = int(value)
                    elif value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif ',' in value and value[0].isdigit():
                        value = [int(x.strip()) for x in value.split(',')]
                    elif ',' in value:
                        value = [x.strip() for x in value.split(',')]
                    
                    CONFIG[full_key] = value


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
            response = requests.get(url, timeout=10)
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


# Platform connectors (base classes)
class PlatformConnector:
    """Base class for platform connectors"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.bots: Dict[str, dict] = {}
    
    def send_message(self, bot_id: str, chat_id: str, text: str, **kwargs) -> dict:
        """Send message to chat"""
        raise NotImplementedError()
    
    def process_webhook(self, payload: dict) -> dict:
        """Process incoming webhook payload"""
        raise NotImplementedError()
    
    def set_webhook(self, bot_id: str, url: str) -> dict:
        """Set webhook URL for bot"""
        raise NotImplementedError()
    
    def delete_webhook(self, bot_id: str) -> dict:
        """Delete webhook for bot"""
        raise NotImplementedError()
    
    def add_bot(self, bot_id: str, config: dict) -> dict:
        """Add bot to platform"""
        self.bots[bot_id] = {
            "bot_id": bot_id,
            "config": config,
            "status": "inactive",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        return {"status": "success", "message": f"Bot {bot_id} added"}
    
    def remove_bot(self, bot_id: str) -> dict:
        """Remove bot from platform"""
        if bot_id in self.bots:
            del self.bots[bot_id]
            return {"status": "success", "message": f"Bot {bot_id} removed"}
        return {"status": "error", "message": f"Bot {bot_id} not found"}


class VKConnector(PlatformConnector):
    """VK platform connector"""
    
    def __init__(self):
        super().__init__("vk")
        self.api_version = "5.131"
    
    def send_message(self, bot_id: str, chat_id: str, text: str, **kwargs) -> dict:
        """Send message via VK API"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        # In real implementation, this would call VK API
        # For demo, just log it
        logger.info(f"VK: Send message to {chat_id}: {text[:100]}")
        
        return {
            "status": "success",
            "message_id": str(uuid.uuid4()),
            "sent_at": datetime.utcnow().isoformat() + "Z"
        }
    
    def process_webhook(self, payload: dict) -> dict:
        """Process VK webhook payload"""
        # In real implementation, parse VK webhook and extract message
        # For demo, just log it
        logger.info(f"VK webhook received: {json.dumps(payload, indent=2)[:500]}")
        
        # Extract message info
        message_id = payload.get("object", {}).get("id", str(uuid.uuid4()))
        
        return {
            "status": "success",
            "message_id": message_id
        }
    
    def set_webhook(self, bot_id: str, url: str) -> dict:
        """Set webhook URL"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        # In real implementation, call VK API to set webhook
        logger.info(f"VK: Setting webhook for bot {bot_id} to {url}")
        bot["webhook_url"] = url
        bot["status"] = "active"
        
        return {"status": "success", "message": "Webhook set"}
    
    def delete_webhook(self, bot_id: str) -> dict:
        """Delete webhook"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        # In real implementation, call VK API to delete webhook
        logger.info(f"VK: Deleting webhook for bot {bot_id}")
        if "webhook_url" in bot:
            del bot["webhook_url"]
        bot["status"] = "inactive"
        
        return {"status": "success", "message": "Webhook deleted"}


class TelegramConnector(PlatformConnector):
    """Telegram platform connector"""
    
    def __init__(self):
        super().__init__("telegram")
        self.api_url = "https://api.telegram.org"
    
    def send_message(self, bot_id: str, chat_id: str, text: str, **kwargs) -> dict:
        """Send message via Telegram API"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        # In real implementation, call Telegram API
        logger.info(f"Telegram: Send message to {chat_id}: {text[:100]}")
        
        return {
            "status": "success",
            "message_id": str(uuid.uuid4()),
            "sent_at": datetime.utcnow().isoformat() + "Z"
        }
    
    def process_webhook(self, payload: dict) -> dict:
        """Process Telegram webhook payload"""
        logger.info(f"Telegram webhook received: {json.dumps(payload, indent=2)[:500]}")
        
        message_id = payload.get("update_id", str(uuid.uuid4()))
        
        return {
            "status": "success",
            "message_id": message_id
        }
    
    def set_webhook(self, bot_id: str, url: str) -> dict:
        """Set webhook URL"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        logger.info(f"Telegram: Setting webhook for bot {bot_id} to {url}")
        bot["webhook_url"] = url
        bot["status"] = "active"
        
        return {"status": "success", "message": "Webhook set"}
    
    def delete_webhook(self, bot_id: str) -> dict:
        """Delete webhook"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        logger.info(f"Telegram: Deleting webhook for bot {bot_id}")
        if "webhook_url" in bot:
            del bot["webhook_url"]
        bot["status"] = "inactive"
        
        return {"status": "success", "message": "Webhook deleted"}


class MAXConnector(PlatformConnector):
    """MAX (MIR) platform connector"""
    
    def __init__(self):
        super().__init__("max")
        self.api_url = "https://api.max.com"
    
    def send_message(self, bot_id: str, chat_id: str, text: str, **kwargs) -> dict:
        """Send message via MAX API"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        logger.info(f"MAX: Send message to {chat_id}: {text[:100]}")
        
        return {
            "status": "success",
            "message_id": str(uuid.uuid4()),
            "sent_at": datetime.utcnow().isoformat() + "Z"
        }
    
    def process_webhook(self, payload: dict) -> dict:
        """Process MAX webhook payload"""
        logger.info(f"MAX webhook received: {json.dumps(payload, indent=2)[:500]}")
        
        message_id = payload.get("event_id", str(uuid.uuid4()))
        
        return {
            "status": "success",
            "message_id": message_id
        }
    
    def set_webhook(self, bot_id: str, url: str) -> dict:
        """Set webhook URL"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        logger.info(f"MAX: Setting webhook for bot {bot_id} to {url}")
        bot["webhook_url"] = url
        bot["status"] = "active"
        
        return {"status": "success", "message": "Webhook set"}
    
    def delete_webhook(self, bot_id: str) -> dict:
        """Delete webhook"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}
        
        logger.info(f"MAX: Deleting webhook for bot {bot_id}")
        if "webhook_url" in bot:
            del bot["webhook_url"]
        bot["status"] = "inactive"
        
        return {"status": "success", "message": "Webhook deleted"}


# Global platform connectors
platform_connectors: Dict[str, PlatformConnector] = {
    "vk": VKConnector(),
    "telegram": TelegramConnector(),
    "max": MAXConnector()
}


# State manager
class StateManager:
    """Manage user conversation states"""
    
    def __init__(self):
        self.states: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.ttl = CONFIG["state_ttl"]
    
    def get_state(self, user_id: str, platform: str, bot_id: str = None) -> Dict[str, Any]:
        """Get user state"""
        key = f"{platform}:{user_id}" + (f":{bot_id}" if bot_id else "")
        
        with self.lock:
            if key in self.states:
                state = self.states[key]
                # Check TTL
                if time.time() - state.get("updated_at", time.time()) > self.ttl:
                    del self.states[key]
                    return {}
                return state
            return {}
    
    def set_state(self, user_id: str, platform: str, state: dict, bot_id: str = None):
        """Set user state"""
        key = f"{platform}:{user_id}" + (f":{bot_id}" if bot_id else "")
        
        state.update({
            "updated_at": time.time(),
            "created_at": state.get("created_at", time.time())
        })
        
        with self.lock:
            self.states[key] = state
    
    def clear_state(self, user_id: str, platform: str, bot_id: str = None) -> bool:
        """Clear user state"""
        key = f"{platform}:{user_id}" + (f":{bot_id}" if bot_id else "")
        
        with self.lock:
            if key in self.states:
                del self.states[key]
                return True
            return False
    
    def cleanup(self):
        """Cleanup expired states"""
        with self.lock:
            now = time.time()
            expired_keys = [
                k for k, state in self.states.items()
                if now - state.get("updated_at", now) > self.ttl
            ]
            for key in expired_keys:
                del self.states[key]
            return len(expired_keys)


# Command router
class CommandRouter:
    """Route commands to appropriate handlers"""
    
    def __init__(self):
        self.handlers: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    def register_handler(self, pattern: str, handler: str, module: str, 
                         priority: int = 100, platforms: list = None, 
                         description: str = "") -> str:
        """Register a command handler"""
        handler_id = str(uuid.uuid4())
        
        with self.lock:
            self.handlers[handler_id] = {
                "handler_id": handler_id,
                "pattern": pattern,
                "handler": handler,
                "module": module,
                "priority": priority,
                "platforms": platforms or CONFIG["supported_platforms"],
                "description": description,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
        
        logger.info(f"Command handler registered: {pattern} -> {module}")
        return handler_id
    
    def unregister_handler(self, handler_id: str) -> bool:
        """Unregister a command handler"""
        with self.lock:
            if handler_id in self.handlers:
                del self.handlers[handler_id]
                logger.info(f"Command handler unregistered: {handler_id}")
                return True
            return False
    
    def find_handler(self, text: str, platform: str) -> Dict[str, Any]:
        """Find matching handler for text"""
        with self.lock:
            best_handler = None
            best_priority = 0
            
            for handler in self.handlers.values():
                # Check platform
                if platform not in handler["platforms"]:
                    continue
                
                # Check pattern
                try:
                    if re.match(handler["pattern"], text):
                        if handler["priority"] > best_priority:
                            best_priority = handler["priority"]
                            best_handler = handler
                except re.error:
                    continue
            
            return best_handler
    
    def process_command(self, bot_id: str, platform: str, user_id: str, 
                        chat_id: str, text: str, message_id: str = None) -> dict:
        """Process incoming command"""
        # Get user auth info
        user_info = call_auth_api(
            f'/api/v1/auth/users/{user_id}',
            'GET',
            headers={'Authorization': f'Bearer admin_token'}  # In real implementation, use proper auth
        )
        
        roles = user_info.get('roles', []) if user_info.get('status') == 'success' else []
        
        # Get user state
        state_manager = StateManager()
        state = state_manager.get_state(user_id, platform, bot_id)
        
        # Find matching handler
        handler = self.find_handler(text, platform)
        
        if handler:
            # Route to module via core
            result = call_core_api('/api/v1/modules/message', 'POST', {
                "to": handler["module"],
                "command": handler["handler"],
                "parameters": {
                    "text": text,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "platform": platform,
                    "roles": roles,
                    "state": state,
                    "message_id": message_id,
                    "bot_id": bot_id
                }
            })
            
            if result.get("status") == "queued":
                # Update state if handler specifies
                new_state = state.copy()
                new_state["last_command"] = text
                new_state["last_handler"] = handler["handler"]
                state_manager.set_state(user_id, platform, new_state, bot_id)
                
                return {
                    "status": "processed",
                    "handler": handler["handler"],
                    "module": handler["module"],
                    "response": result
                }
        
        # No handler found - pass to LLM
        logger.info(f"No command handler found for: {text}, passing to LLM")
        
        # Try to match with menu
        menu_result = call_core_api('/api/v1/modules/multichat/menu', 'POST', {
            "text": text,
            "user_id": user_id,
            "roles": roles
        })
        
        if menu_result.get("status") == "success":
            return {
                "status": "processed",
                "action": "menu_match",
                "target_module": "menu",
                "response": menu_result
            }
        
        # Pass to LLM module
        llm_result = call_core_api('/api/v1/modules/llm', 'POST', {
            "command": "process_query",
            "parameters": {
                "text": text,
                "user_id": user_id,
                "platform": platform,
                "roles": roles,
                "state": state
            }
        })
        
        return {
            "status": "processed",
            "action": "llm_response",
            "target_module": "llm",
            "response": llm_result
        }


# Global instances
state_manager = StateManager()
command_router = CommandRouter()


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for multichat module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            # List platforms
            if path == "/api/v1/platforms":
                platform_list = []
                for platform_name in CONFIG["supported_platforms"]:
                    connector = platform_connectors.get(platform_name)
                    if connector:
                        platform_list.append({
                            "name": platform_name,
                            "enabled": True,
                            "webhook_url": f"{CONFIG['listen_address']}:{CONFIG['listen_port']}{CONFIG['webhook_path']}/{platform_name}",
                            "status": "active" if connector.bots else "inactive",
                            "last_check": datetime.utcnow().isoformat() + "Z",
                            "message_count": 0  # Would track in real implementation
                        })
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "platforms": platform_list,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get platform status
            elif path.startswith("/api/v1/platforms/"):
                parts = path.split("/")
                platform_name = parts[3]
                
                if len(parts) == 4:
                    connector = platform_connectors.get(platform_name)
                    if connector:
                        bots_list = []
                        for bot_id, bot_info in connector.bots.items():
                            bots_list.append({
                                "bot_id": bot_id,
                                "name": bot_info.get("name", bot_id),
                                "token": "*****" if bot_info.get("token") else None,
                                "status": bot_info.get("status", "unknown"),
                                "last_message": bot_info.get("last_message"),
                                "message_count": bot_info.get("message_count", 0),
                                "user_count": bot_info.get("user_count", 0)
                            })
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "platform": platform_name,
                            "enabled": True,
                            "status": "active",
                            "webhook_url": f"{CONFIG['listen_address']}:{CONFIG['listen_port']}{CONFIG['webhook_path']}/{platform_name}",
                            "webhook_verified": True,
                            "bots": bots_list,
                            "message_queue": {
                                "queued": 0,
                                "processing": 0,
                                "failed": 0
                            }
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                    else:
                        self.send_error(404, f"Platform {platform_name} not found")
                
                elif len(parts) >= 5 and parts[4] == "stats":
                    connector = platform_connectors.get(platform_name)
                    if connector:
                        total_messages = sum(b.get("message_count", 0) for b in connector.bots.values())
                        total_users = sum(b.get("user_count", 0) for b in connector.bots.values())
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "statistics": {
                                "bots": len(connector.bots),
                                "messages_received": total_messages,
                                "messages_sent": total_messages,
                                "active_users": total_users
                            }
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
            
            # List bots
            elif path == "/api/v1/bots":
                all_bots = []
                for platform_name, connector in platform_connectors.items():
                    for bot_id, bot_info in connector.bots.items():
                        all_bots.append({
                            "bot_id": bot_id,
                            "name": bot_info.get("name", bot_id),
                            "platform": platform_name,
                            "token": "*****",
                            "status": bot_info.get("status", "unknown"),
                            "created_at": bot_info.get("created_at"),
                            "last_message": bot_info.get("last_message"),
                            "message_count": bot_info.get("message_count", 0),
                            "user_count": bot_info.get("user_count", 0)
                        })
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "bots": all_bots,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get bot details
            elif path.startswith("/api/v1/bots/"):
                parts = path.split("/")
                bot_id = parts[3]
                
                if len(parts) == 4:
                    # Find bot across all platforms
                    bot_found = None
                    platform_name = None
                    for p_name, connector in platform_connectors.items():
                        if bot_id in connector.bots:
                            bot_found = connector.bots[bot_id]
                            platform_name = p_name
                            break
                    
                    if bot_found:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "bot_id": bot_id,
                            "name": bot_found.get("name", bot_id),
                            "platform": platform_name,
                            "status": bot_found.get("status", "unknown"),
                            "config": {k: v for k, v in bot_found.get("config", {}).items() if k != "token"},
                            "webhook_info": {
                                "url": bot_found.get("webhook_url"),
                                "verified": True
                            },
                            "statistics": {
                                "message_count": bot_found.get("message_count", 0),
                                "user_count": bot_found.get("user_count", 0)
                            },
                            "created_at": bot_found.get("created_at"),
                            "updated_at": datetime.utcnow().isoformat() + "Z"
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                    else:
                        self.send_error(404, f"Bot {bot_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "stats":
                    bot_id = parts[3]
                    # Find bot and get stats
                    bot_found = None
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            bot_found = connector.bots[bot_id]
                            break
                    
                    if bot_found:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "statistics": {
                                "messages_received": bot_found.get("message_count", 0),
                                "messages_sent": bot_found.get("message_count", 0),
                                "active_users": bot_found.get("user_count", 0),
                                "new_users_today": 0,
                                "most_used_commands": []
                            }
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
            
            # List commands
            elif path == "/api/v1/commands":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "commands": list(command_router.handlers.values()),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get user state
            elif path.startswith("/api/v1/users/"):
                parts = path.split("/")
                platform_name = parts[3]
                user_id = parts[4]
                
                if len(parts) >= 7 and parts[5] == "state":
                    bot_id = parts[6] if len(parts) >= 8 else None
                    state = state_manager.get_state(user_id, platform_name, bot_id)
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "state": state
                    }
                    self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Health check
            elif path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                
                platform_statuses = []
                total_bots = 0
                for platform_name, connector in platform_connectors.items():
                    bot_count = len(connector.bots)
                    total_bots += bot_count
                    platform_statuses.append({
                        "platform": platform_name,
                        "status": "active" if bot_count > 0 else "inactive",
                        "bots": bot_count
                    })
                
                response = {
                    "status": "healthy" if total_bots > 0 else "degraded",
                    "platforms": platform_statuses,
                    "active_bots": total_bots,
                    "message_queue": {"size": message_queue.qsize()},
                    "error_rate": 0.0,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
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
            
            # Webhook endpoints
            if path.startswith(f"{CONFIG['webhook_path']}/"):
                parts = path.split("/")
                platform_name = parts[-1]
                
                connector = platform_connectors.get(platform_name)
                if connector:
                    result = connector.process_webhook(data)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_error(404, f"Platform {platform_name} not found")
                return
            
            # Add bot
            if path == "/api/v1/bots":
                required = ["name", "platform", "token"]
                if all(k in data for k in required):
                    platform_name = data["platform"]
                    connector = platform_connectors.get(platform_name)
                    
                    if connector:
                        bot_id = str(uuid.uuid4())
                        bot_config = {
                            "name": data["name"],
                            "token": data["token"],
                            "webhook_url": data.get("webhook_url"),
                            "config": data.get("config", {})
                        }
                        
                        result = connector.add_bot(bot_id, bot_config)
                        
                        if result["status"] == "success":
                            # Try to set webhook
                            if data.get("webhook_url"):
                                connector.set_webhook(bot_id, data["webhook_url"])
                            
                            self.send_response(201)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            result["bot_id"] = bot_id
                            self.wfile.write(json.dumps(result).encode())
                        else:
                            self.send_error(400, result.get("message", "Failed to add bot"))
                    else:
                        self.send_error(400, f"Platform {platform_name} not supported")
                else:
                    self.send_error(400, "Missing required fields: name, platform, token")
            
            # Set webhook
            elif path.startswith("/api/v1/bots/"):
                parts = path.split("/")
                bot_id = parts[3]
                
                if len(parts) >= 5 and parts[4] == "webhook":
                    url = data.get("url", "")
                    
                    # Find bot
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            result = connector.set_webhook(bot_id, url)
                            self.send_response(200 if result["status"] == "success" else 400)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode())
                            return
                    
                    self.send_error(404, f"Bot {bot_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "send":
                    # Send message
                    platform_name = None
                    for p_name, connector in platform_connectors.items():
                        if bot_id in connector.bots:
                            platform_name = p_name
                            break
                    
                    if platform_name:
                        chat_id = data.get("chat_id", "")
                        text = data.get("text", "")
                        
                        if not text:
                            self.send_error(400, "Message text is required")
                            return
                        
                        if len(text) > CONFIG["max_message_length"]:
                            self.send_error(400, f"Message too long (max {CONFIG['max_message_length']})")
                            return
                        
                        connector = platform_connectors[platform_name]
                        result = connector.send_message(bot_id, chat_id, text)
                        
                        self.send_response(200 if result["status"] == "success" else 400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode())
                    else:
                        self.send_error(404, f"Bot {bot_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "test":
                    # Test bot connection
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            # For demo, just return success
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "success",
                                "message": "Connection test passed",
                                "details": {"connected": True}
                            }
                            self.wfile.write(json.dumps(response).encode())
                            return
                    
                    self.send_error(404, f"Bot {bot_id} not found")
            
            # Register command handler
            elif path == "/api/v1/commands/register":
                required = ["pattern", "handler", "module"]
                if all(k in data for k in required):
                    handler_id = command_router.register_handler(
                        data["pattern"],
                        data["handler"],
                        data["module"],
                        data.get("priority", 100),
                        data.get("platforms"),
                        data.get("description", "")
                    )
                    
                    self.send_response(201)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "command_id": handler_id,
                        "message": "Command handler registered"
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_error(400, "Missing required fields: pattern, handler, module")
            
            # Process command
            elif path == "/api/v1/process/command":
                required = ["text", "user_id", "chat_id", "platform"]
                if all(k in data for k in required):
                    result = command_router.process_command(
                        data.get("bot_id"),
                        data["platform"],
                        data["user_id"],
                        data["chat_id"],
                        data["text"],
                        data.get("message_id")
                    )
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_error(400, "Missing required fields: text, user_id, chat_id, platform")
            
            # Enable/disable platform
            elif path.startswith("/api/v1/platforms/"):
                parts = path.split("/")
                platform_name = parts[3]
                
                if len(parts) >= 5:
                    if parts[4] == "enable":
                        # For demo, platforms are always enabled
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": f"Platform {platform_name} enabled"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    
                    elif parts[4] == "disable":
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": f"Platform {platform_name} disabled"
                        }
                        self.wfile.write(json.dumps(response).encode())
            
            # Update user state
            elif path.startswith("/api/v1/users/"):
                parts = path.split("/")
                platform_name = parts[3]
                user_id = parts[4]
                
                if len(parts) >= 7 and parts[5] == "state":
                    bot_id = parts[6] if len(parts) >= 8 else None
                    state = data
                    
                    state_manager.set_state(user_id, platform_name, state, bot_id)
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "message": "State updated"
                    }
                    self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}")
            self.send_error(500, str(e))
    
    def do_PUT(self):
        """Handle PUT requests"""
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
            
            # Update bot
            if path.startswith("/api/v1/bots/"):
                parts = path.split("/")
                bot_id = parts[3]
                
                if len(parts) == 4:
                    # Find bot and update
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            bot_info = connector.bots[bot_id]
                            for key, value in data.items():
                                if key != "bot_id":
                                    bot_info["config"][key] = value
                            
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "success",
                                "message": f"Bot {bot_id} updated"
                            }
                            self.wfile.write(json.dumps(response).encode())
                            return
                    
                    self.send_error(404, f"Bot {bot_id} not found")
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling PUT {path}: {e}")
            self.send_error(500, str(e))
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            # Delete bot
            if path.startswith("/api/v1/bots/"):
                parts = path.split("/")
                bot_id = parts[3]
                
                if len(parts) == 4:
                    # Find and delete bot
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            result = connector.remove_bot(bot_id)
                            self.send_response(200 if result["status"] == "success" else 404)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode())
                            return
                    
                    self.send_error(404, f"Bot {bot_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "webhook":
                    # Delete webhook
                    bot_id = parts[3]
                    for connector in platform_connectors.values():
                        if bot_id in connector.bots:
                            result = connector.delete_webhook(bot_id)
                            self.send_response(200 if result["status"] == "success" else 404)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode())
                            return
                    
                    self.send_error(404, f"Bot {bot_id} not found")
            
            # Unregister command handler
            elif path.startswith("/api/v1/commands/"):
                parts = path.split("/")
                command_id = parts[3]
                
                if len(parts) == 4:
                    if command_router.unregister_handler(command_id):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": f"Command handler {command_id} unregistered"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, f"Command handler {command_id} not found")
            
            # Clear user state
            elif path.startswith("/api/v1/users/"):
                parts = path.split("/")
                platform_name = parts[3]
                user_id = parts[4]
                
                if len(parts) >= 7 and parts[5] == "state":
                    bot_id = parts[6] if len(parts) >= 8 else None
                    
                    if state_manager.clear_state(user_id, platform_name, bot_id):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": "State cleared"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, "State not found")
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling DELETE {path}: {e}")
            self.send_error(500, str(e))


def process_message_queue():
    """Process messages from queue"""
    logger.info("Message processor started")
    
    while True:
        try:
            # Process webhook messages
            # In real implementation, this would handle queued messages
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in message processor: {e}")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot Multi-chat Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Load configuration
    load_config()
    
    logger.info(f"Starting UniBot Multi-chat Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    logger.info(f"Supported platforms: {', '.join(CONFIG['supported_platforms'])}")
    
    # Start message processor thread
    processor_thread = threading.Thread(target=process_message_queue, daemon=True)
    processor_thread.start()
    
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
        logger.info("Multi-chat module stopped")


if __name__ == "__main__":
    main()
