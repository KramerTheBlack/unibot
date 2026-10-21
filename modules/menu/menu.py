#!/usr/bin/env python3
"""
UniBot Menu Module
Menu and navigation management module for UniBot
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import threading
import copy
import logging
import logging.handlers
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple
import hashlib

# Module metadata
MODULE_NAME = "menu"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5005,
    "menu_file": "menu.json",
    "menu_path": "/var/lib/unibot/menu",
    "max_depth": 5,
    "max_buttons_per_row": 3,
    "button_text_length_limit": 20,
    "default_platform": "all",
    "show_back_button": True,
    "back_button_text": "Назад",
    "show_main_button": True,
    "main_button_text": "Главное меню",
    "log_level": "INFO",
    "log_file": "/var/log/unibot/menu.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "core_endpoint": "http://core:5000",
    "auth_endpoint": "http://auth:5001",
    "multichat_endpoint": "http://multichat:5003"
}

# Global state
menu: Dict[str, Any] = {}
menu_version: str = "1.0.0"
menu_hash: str = ""
user_states: Dict[str, Dict[str, Any]] = {}
navigation_history: Dict[str, List[Dict[str, Any]]] = {}

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
                    
                    CONFIG[full_key] = value


def load_menu():
    """Load menu from file"""
    global menu, menu_hash
    
    menu_path = os.path.join(CONFIG["menu_path"], CONFIG["menu_file"])
    
    # Create default menu if not exists
    if not os.path.exists(menu_path):
        os.makedirs(CONFIG["menu_path"], exist_ok=True)
        create_default_menu(menu_path)
    
    # Load menu file
    try:
        with open(menu_path, 'r', encoding='utf-8') as f:
            menu = json.load(f)
        
        # Calculate hash
        menu_hash = hashlib.md5(json.dumps(menu, sort_keys=True).encode()).hexdigest()
        
        logger.info(f"Menu loaded from {menu_path}, {len(menu)} items")
        return menu, menu_hash
    except Exception as e:
        logger.error(f"Error loading menu: {e}")
        # Create default menu on error
        create_default_menu(menu_path)
        with open(menu_path, 'r', encoding='utf-8') as f:
            menu = json.load(f)
        menu_hash = hashlib.md5(json.dumps(menu, sort_keys=True).encode()).hexdigest()
        return menu, menu_hash


def save_menu():
    """Save menu to file"""
    global menu, menu_hash
    
    menu_path = os.path.join(CONFIG["menu_path"], CONFIG["menu_file"])
    
    try:
        # Create directory if not exists
        if not os.path.exists(CONFIG["menu_path"]):
            os.makedirs(CONFIG["menu_path"], exist_ok=True)
        
        # Save menu
        with open(menu_path, 'w', encoding='utf-8') as f:
            json.dump(menu, f, indent=2, ensure_ascii=False)
        
        # Calculate hash
        menu_hash = hashlib.md5(json.dumps(menu, sort_keys=True).encode()).hexdigest()
        
        logger.info(f"Menu saved to {menu_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving menu: {e}")
        return False


def create_default_menu(menu_path: str):
    """Create default menu structure"""
    default_menu = {
        "metadata": {
            "version": "1.0.0",
            "description": "Default UniBot menu",
            "created": datetime.utcnow().isoformat() + "Z",
            "updated": datetime.utcnow().isoformat() + "Z"
        },
        "/": {
            "path": "/",
            "text": "Главное меню",
            "type": "menu",
            "description": "Основное меню бота",
            "icon": "🏠",
            "children": {}
        },
        "/start": {
            "path": "/start",
            "text": "Начать",
            "type": "command",
            "command": "/start",
            "description": "Начать работу с ботом",
            "access": {
                "roles": ["anonymous", "customer", "admin"],
                "min_role": "anonymous"
            },
            "platform": "all",
            "order": 10
        },
        "/help": {
            "path": "/help",
            "text": "Помощь",
            "type": "command",
            "command": "/help",
            "description": "Получить помощь",
            "access": {
                "roles": ["anonymous", "customer", "admin"],
                "min_role": "anonymous"
            },
            "platform": "all",
            "order": 20
        },
        "/menu": {
            "path": "/menu",
            "text": "Меню",
            "type": "menu",
            "description": "Полное меню бота",
            "icon": "📋",
            "children": {}
        },
        "/admin": {
            "path": "/admin",
            "text": "Администрирование",
            "type": "menu",
            "description": "Административные функции",
            "icon": "👑",
            "access": {
                "roles": ["admin"],
                "min_role": "admin"
            },
            "platform": "all",
            "order": 100,
            "children": {
                "/admin/users": {
                    "path": "/admin/users",
                    "text": "Управление пользователями",
                    "type": "action",
                    "action": "list_users",
                    "module": "auth",
                    "description": "Список пользователей",
                    "access": {
                        "roles": ["admin"],
                        "min_role": "admin"
                    },
                    "platform": "all",
                    "order": 10
                },
                "/admin/modules": {
                    "path": "/admin/modules",
                    "text": "Управление модулями",
                    "type": "action",
                    "action": "list_modules",
                    "module": "core",
                    "description": "Список модулей",
                    "access": {
                        "roles": ["admin"],
                        "min_role": "admin"
                    },
                    "platform": "all",
                    "order": 20
                },
                "/admin/settings": {
                    "path": "/admin/settings",
                    "text": "Настройки",
                    "type": "action",
                    "action": "open_settings",
                    "module": "web",
                    "description": "Настройки бота",
                    "access": {
                        "roles": ["admin"],
                        "min_role": "admin"
                    },
                    "platform": "all",
                    "order": 30
                }
            }
        },
        "/services": {
            "path": "/services",
            "text": "Сервисы",
            "type": "menu",
            "description": "Дополнительные сервисы",
            "icon": "🛠️",
            "access": {
                "roles": ["customer", "admin"],
                "min_role": "customer"
            },
            "platform": "all",
            "order": 50,
            "children": {}
        },
        "/apps": {
            "path": "/apps",
            "text": "Приложения",
            "type": "menu",
            "description": "Дополнительные приложения",
            "icon": "📱",
            "access": {
                "roles": ["customer", "admin"],
                "min_role": "customer"
            },
            "platform": "all",
            "order": 60,
            "children": {}
        }
    }
    
    # Add children to parent menus
    default_menu["/menu"]["children"] = {
        "/start": copy.deepcopy(default_menu["/start"]),
        "/help": copy.deepcopy(default_menu["/help"]),
        "/admin": copy.deepcopy(default_menu["/admin"]),
        "/services": copy.deepcopy(default_menu["/services"]),
        "/apps": copy.deepcopy(default_menu["/apps"])
    }
    
    try:
        with open(menu_path, 'w', encoding='utf-8') as f:
            json.dump(default_menu, f, indent=2, ensure_ascii=False)
        logger.info(f"Default menu created at {menu_path}")
    except Exception as e:
        logger.error(f"Error creating default menu: {e}")


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


# Menu manager
class MenuManager:
    """Manage menu structure"""
    
    def __init__(self, menu_data: dict):
        self.menu = menu_data
        self.lock = threading.Lock()
    
    def get_menu(self, path: str = "/") -> dict:
        """Get menu at specific path"""
        with self.lock:
            return self.menu.get(path, {})
    
    def get_full_menu(self) -> dict:
        """Get full menu"""
        with self.lock:
            return copy.deepcopy(self.menu)
    
    def get_submenu(self, path: str) -> dict:
        """Get submenu items"""
        menu_item = self.get_menu(path)
        if not menu_item:
            return {"status": "error", "error": f"Path {path} not found"}
        
        # Build submenu structure
        submenu = {
            "path": path,
            "menu": menu_item,
            "items": []
        }
        
        # Add back button
        if path != "/" and CONFIG["show_back_button"]:
            parent_path = "/".join(path.split("/")[:-1]) or "/"
            submenu["items"].append({
                "type": "back",
                "text": CONFIG["back_button_text"],
                "path": parent_path,
                "order": -1000
            })
        
        # Add main button
        if path != "/" and CONFIG["show_main_button"]:
            submenu["items"].append({
                "type": "menu",
                "text": CONFIG["main_button_text"],
                "path": "/",
                "order": -999
            })
        
        # Add children
        children = menu_item.get("children", {})
        for child_path, child_item in children.items():
            # Check access
            if self.check_access(child_item, None):
                item = copy.deepcopy(child_item)
                item["path"] = child_path
                submenu["items"].append(item)
        
        # Sort by order
        submenu["items"].sort(key=lambda x: x.get("order", 0))
        
        return submenu
    
    def check_access(self, menu_item: dict, user_roles: list = None) -> bool:
        """Check if user has access to menu item"""
        if user_roles is None:
            return True  # No user specified, assume access
        
        access = menu_item.get("access", {})
        if not access:
            return True
        
        required_roles = access.get("roles", [])
        min_role = access.get("min_role", "anonymous")
        
        # Check if user has any required role
        if required_roles:
            return any(role in user_roles for role in required_roles)
        
        # Check minimum role
        role_hierarchy = ["anonymous", "customer", "admin"]
        try:
            user_max_role = max(role_hierarchy.index(r) for r in user_roles if r in role_hierarchy)
            min_role_idx = role_hierarchy.index(min_role)
            return user_max_role >= min_role_idx
        except (ValueError, IndexError):
            return False
    
    def create_item(self, path: str, item_data: dict) -> dict:
        """Create menu item"""
        with self.lock:
            if path in self.menu:
                return {"status": "error", "message": f"Path {path} already exists"}
            
            # Validate path
            if not self.validate_path(path):
                return {"status": "error", "message": "Invalid path format"}
            
            # Check depth
            depth = len([p for p in path.split("/") if p])
            if depth > CONFIG["max_depth"]:
                return {"status": "error", "message": f"Maximum depth {CONFIG['max_depth']} exceeded"}
            
            # Create path hierarchy
            path_parts = path.strip("/").split("/")
            current_path = "/"
            
            for i, part in enumerate(path_parts):
                part_path = f"/{current_path}{part}" if current_path == "/" else f"{current_path}/{part}"
                
                if i < len(path_parts) - 1:
                    # Create parent menu if not exists
                    if part_path not in self.menu:
                        self.menu[part_path] = {
                            "path": part_path,
                            "text": part,
                            "type": "menu",
                            "description": "",
                            "children": {}
                        }
                else:
                    # Set item data
                    item_data["path"] = part_path
                    self.menu[part_path] = item_data
                
                current_path = part_path
            
            # Save menu
            save_menu()
            
            logger.info(f"Menu item created: {path}")
            return {"status": "success", "path": path, "message": "Menu item created"}
    
    def update_item(self, path: str, item_data: dict) -> dict:
        """Update menu item"""
        with self.lock:
            if path not in self.menu:
                return {"status": "error", "message": f"Path {path} not found"}
            
            # Don't allow changing path
            if "path" in item_data:
                del item_data["path"]
            
            # Update item
            self.menu[path].update(item_data)
            
            # Save menu
            save_menu()
            
            logger.info(f"Menu item updated: {path}")
            return {"status": "success", "path": path, "message": "Menu item updated"}
    
    def delete_item(self, path: str) -> dict:
        """Delete menu item"""
        with self.lock:
            if path not in self.menu:
                return {"status": "error", "message": f"Path {path} not found"}
            
            # Don't allow deleting root
            if path == "/":
                return {"status": "error", "message": "Cannot delete root menu"}
            
            # Delete item
            del self.menu[path]
            
            # Clean up empty parent menus (optional)
            # For now, just delete the item
            
            # Save menu
            save_menu()
            
            logger.info(f"Menu item deleted: {path}")
            return {"status": "success", "path": path, "message": "Menu item deleted"}
    
    def validate_path(self, path: str) -> bool:
        """Validate path format"""
        if not path:
            return False
        
        if not path.startswith("/"):
            return False
        
        # Check for double slashes
        if "//" in path:
            return False
        
        # Check for special characters
        parts = path.strip("/").split("/")
        for part in parts:
            if not part or any(c in part for c in "?#[]@!") or part.startswith("."):
                return False
        
        return True
    
    def reorder_items(self, parent: str, order: list) -> dict:
        """Reorder menu items under a parent"""
        with self.lock:
            parent_menu = self.get_menu(parent)
            if not parent_menu:
                return {"status": "error", "message": f"Parent {parent} not found"}
            
            children = parent_menu.get("children", {})
            
            # Create new children dict with new order
            new_children = {}
            for i, path in enumerate(order):
                if path in children:
                    new_children[path] = children[path]
                    new_children[path]["order"] = i
            
            # Add any missing children at the end
            for path, item in children.items():
                if path not in new_children:
                    new_children[path] = item
                    new_children[path]["order"] = len(new_children)
            
            # Update parent
            parent_menu["children"] = new_children
            self.menu[parent] = parent_menu
            
            # Save menu
            save_menu()
            
            logger.info(f"Menu items reordered under {parent}")
            return {"status": "success", "message": "Menu items reordered"}
    
    def filter_by_access(self, user_roles: list, platform: str = None) -> dict:
        """Filter menu by user access"""
        with self.lock:
            filtered_menu = {}
            platform = platform or CONFIG["default_platform"]
            
            for path, item in self.menu.items():
                # Check platform
                item_platform = item.get("platform", "all")
                if item_platform != "all" and item_platform != platform:
                    continue
                
                # Check access
                if self.check_access(item, user_roles):
                    # Add to filtered menu
                    filtered_menu[path] = copy.deepcopy(item)
                    
                    # Filter children recursively
                    if item.get("type") == "menu" and "children" in item:
                        children = item["children"]
                        filtered_children = {}
                        
                        for child_path, child_item in children.items():
                            child_full_path = child_path
                            if child_full_path in self.menu:
                                child_menu_item = self.menu[child_full_path]
                                child_platform = child_menu_item.get("platform", "all")
                                
                                if child_platform == "all" or child_platform == platform:
                                    if self.check_access(child_menu_item, user_roles):
                                        filtered_children[child_path] = copy.deepcopy(child_menu_item)
                        
                        filtered_menu[path]["children"] = filtered_children
            
            return filtered_menu


# Navigation manager
class NavigationManager:
    """Manage user navigation state"""
    
    def __init__(self):
        self.user_states: Dict[str, Dict[str, Any]] = {}
        self.navigation_history: Dict[str, List[Dict[str, Any]]] = {}
        self.lock = threading.Lock()
    
    def get_state(self, user_id: str, platform: str) -> dict:
        """Get user navigation state"""
        key = f"{platform}:{user_id}"
        
        with self.lock:
            if key in self.user_states:
                return self.user_states[key]
            
            # Return default state
            return {
                "user_id": user_id,
                "platform": platform,
                "current_path": "/",
                "history": [],
                "state": {}
            }
    
    def navigate(self, user_id: str, platform: str, path: str, from_path: str = None) -> dict:
        """Navigate to path"""
        key = f"{platform}:{user_id}"
        
        with self.lock:
            # Initialize if not exists
            if key not in self.user_states:
                self.user_states[key] = {
                    "user_id": user_id,
                    "platform": platform,
                    "current_path": "/",
                    "history": [],
                    "state": {}
                }
            
            state = self.user_states[key]
            current_path = state.get("current_path", "/")
            history = state.get("history", [])
            
            # If path is same as current, do nothing
            if path == current_path:
                return {
                    "status": "success",
                    "path": path,
                    "menu": menu_manager.get_menu(path),
                    "history": history,
                    "action": "none"
                }
            
            # Add to history
            history.append({
                "path": path,
                "from": from_path or current_path,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "action": "navigate"
            })
            
            # Limit history
            if len(history) > 100:
                history = history[-50:]
            
            # Update state
            state["current_path"] = path
            state["history"] = history
            state["state"] = {}
            
            # Get menu
            menu_item = menu_manager.get_menu(path)
            
            # Check if it's an action
            action = None
            if menu_item and menu_item.get("type") == "action":
                action = {
                    "action": menu_item.get("action"),
                    "module": menu_item.get("module"),
                    "parameters": menu_item.get("parameters", {})
                }
            
            # Check if it's a command
            command = None
            if menu_item and menu_item.get("type") == "command":
                command = menu_item.get("command")
            
            logger.info(f"User {user_id} navigated from {from_path or current_path} to {path}")
            
            return {
                "status": "success",
                "path": path,
                "menu": menu_item,
                "history": history,
                "action": action,
                "command": command
            }
    
    def go_back(self, user_id: str, platform: str) -> dict:
        """Go back to previous menu"""
        key = f"{platform}:{user_id}"
        
        with self.lock:
            if key not in self.user_states:
                return {"status": "error", "message": "No navigation history"}
            
            state = self.user_states[key]
            history = state.get("history", [])
            
            if len(history) < 2:
                # Go to root
                return self.navigate(user_id, platform, "/")
            
            # Get previous path
            prev_item = history[-2]
            prev_path = prev_item.get("from", "/")
            
            # Remove last item from history (going back)
            state["history"] = history[:-1]
            state["current_path"] = prev_path
            
            # Get menu
            menu_item = menu_manager.get_menu(prev_path)
            
            logger.info(f"User {user_id} went back to {prev_path}")
            
            return {
                "status": "success",
                "path": prev_path,
                "menu": menu_item,
                "history": state["history"],
                "action": "back"
            }
    
    def go_main(self, user_id: str, platform: str) -> dict:
        """Go to main menu"""
        return self.navigate(user_id, platform, "/")
    
    def get_history(self, user_id: str, platform: str) -> dict:
        """Get navigation history"""
        key = f"{platform}:{user_id}"
        
        with self.lock:
            if key in self.user_states:
                return {
                    "status": "success",
                    "history": self.user_states[key].get("history", [])
                }
            return {"status": "success", "history": []}


# Renderer
class MenuRenderer:
    """Render menu for different platforms"""
    
    def __init__(self):
        self.platform_configs = {
            "vk": {
                "max_buttons_per_row": 3,
                "button_text_length_limit": 20,
                "supports_keyboards": True,
                "supports_inline_keyboards": True
            },
            "telegram": {
                "max_buttons_per_row": 8,
                "button_text_length_limit": 40,
                "supports_keyboards": True,
                "supports_inline_keyboards": True
            },
            "max": {
                "max_buttons_per_row": 4,
                "button_text_length_limit": 30,
                "supports_keyboards": True,
                "supports_inline_keyboards": True
            }
        }
    
    def render(self, path: str, platform: str, user_id: str = None) -> dict:
        """Render menu for platform"""
        submenu = menu_manager.get_submenu(path)
        
        if submenu.get("status") == "error":
            return submenu
        
        # Get platform config
        platform_config = self.platform_configs.get(platform, self.platform_configs["all"])
        
        # Get user roles if provided
        user_roles = []
        if user_id:
            user_info = call_auth_api(f'/api/v1/auth/users/{user_id}', 'GET')
            if user_info.get("status") == "success":
                user_roles = user_info.get("roles", [])
        
        # Filter items by access
        items = []
        for item in submenu.get("items", []):
            if menu_manager.check_access(item, user_roles):
                items.append(item)
        
        # Group into rows
        max_per_row = platform_config.get("max_buttons_per_row", CONFIG["max_buttons_per_row"])
        rows = []
        current_row = []
        
        for item in items:
            # Truncate text if needed
            text = item.get("text", "")
            max_length = platform_config.get("button_text_length_limit", CONFIG["button_text_length_limit"])
            if len(text) > max_length:
                text = text[:max_length-3] + "..."
            
            button = {
                "text": text,
                "type": item.get("type", "text")
            }
            
            # Add path for menu type
            if item.get("type") == "menu":
                button["path"] = item.get("path")
            
            # Add command for command type
            if item.get("type") == "command":
                button["command"] = item.get("command")
            
            # Add action for action type
            if item.get("type") == "action":
                button["action"] = item.get("action")
                button["module"] = item.get("module")
                button["parameters"] = item.get("parameters", {})
            
            # Add callback for back/main buttons
            if item.get("type") == "back":
                button["path"] = item.get("path")
                button["action"] = "go_back"
            
            current_row.append(button)
            
            if len(current_row) >= max_per_row:
                rows.append(current_row)
                current_row = []
        
        if current_row:
            rows.append(current_row)
        
        # Create platform-specific keyboard
        if platform == "vk":
            keyboard = {
                "type": "keyboard",
                "rows": rows,
                "one_time": False,
                "resize_keyboard": True
            }
        elif platform == "telegram":
            keyboard = {
                "type": "reply_keyboard_markup",
                "keyboard": rows,
                "resize_keyboard": True,
                "one_time_keyboard": False
            }
        elif platform == "max":
            keyboard = {
                "type": "keyboard",
                "buttons": rows,
                "one_time": False
            }
        else:
            keyboard = {
                "type": "keyboard",
                "rows": rows
            }
        
        return {
            "status": "success",
            "platform": platform,
            "keyboard": keyboard,
            "menu": submenu.get("menu", {}),
            "items": items
        }
    
    def render_inline(self, path: str, platform: str, user_id: str = None) -> dict:
        """Render inline keyboard for platform"""
        result = self.render(path, platform, user_id)
        
        if result.get("status") != "success":
            return result
        
        keyboard = result.get("keyboard", {})
        
        # Convert to inline keyboard
        if platform == "telegram":
            inline_keyboard = []
            for row in keyboard.get("keyboard", []):
                inline_row = []
                for button in row:
                    inline_button = {"text": button.get("text")}
                    
                    # Convert callback data
                    if button.get("type") == "menu" and "path" in button:
                        inline_button["callback_data"] = f"menu:{button['path']}"
                    elif button.get("type") == "command":
                        inline_button["callback_data"] = f"cmd:{button.get('command', '')}"
                    elif button.get("type") == "action":
                        action_data = {
                            "action": button.get("action"),
                            "module": button.get("module"),
                            "parameters": button.get("parameters", {})
                        }
                        inline_button["callback_data"] = f"action:{json.dumps(action_data)}"
                    elif button.get("type") == "back":
                        inline_button["callback_data"] = "back"
                    
                    inline_row.append(inline_button)
                inline_keyboard.append(inline_row)
            
            return {
                "status": "success",
                "inline_keyboard": inline_keyboard
            }
        
        return {
            "status": "success",
            "inline_keyboard": keyboard
        }


# Global instances
menu_manager = MenuManager({})
navigation_manager = NavigationManager()
menu_renderer = MenuRenderer()


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for menu module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            # Get full menu
            if path == "/api/v1/menu":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "menu": menu_manager.get_full_menu(),
                    "version": menu_version,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "hash": menu_hash
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get submenu
            elif path.startswith("/api/v1/menu/"):
                menu_path = path[11:]  # Remove "/api/v1/menu/"
                platform = params.get("platform", [CONFIG["default_platform"]])[0]
                
                submenu = menu_manager.get_submenu(menu_path)
                
                if submenu.get("status") == "error":
                    self.send_error(404, submenu.get("error", "Menu not found"))
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(submenu, indent=2).encode())
            
            # Get menu version
            elif path == "/api/v1/menu/version":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "version": menu_version,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "hash": menu_hash
                }
                self.wfile.write(json.dumps(response).encode())
            
            # Get statistics
            elif path == "/api/v1/menu/stats":
                total_items = len([p for p in menu.keys() if not p.startswith("metadata")])
                by_type = {}
                max_depth = 0
                
                for path, item in menu.items():
                    if path.startswith("metadata"):
                        continue
                    
                    item_type = item.get("type", "unknown")
                    by_type[item_type] = by_type.get(item_type, 0) + 1
                    
                    # Calculate depth
                    depth = len([p for p in path.split("/") if p])
                    if depth > max_depth:
                        max_depth = depth
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "statistics": {
                        "total_items": total_items,
                        "by_type": by_type,
                        "max_depth": max_depth,
                        "by_platform": {}
                    }
                }
                self.wfile.write(json.dumps(response).encode())
            
            # Health check
            elif path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "loaded": len(menu) > 0,
                    "menu_items": len([p for p in menu.keys() if not p.startswith("metadata")]),
                    "active_users": len(navigation_manager.user_states),
                    "error_rate": 0.0,
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
            
            if post_data:
                try:
                    data = json.loads(post_data.decode())
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
            
            # Create menu item
            if path == "/api/v1/menu":
                menu_path = data.get("path", "")
                if not menu_path:
                    self.send_error(400, "Path is required")
                    return
                
                result = menu_manager.create_item(menu_path, data)
                
                if result.get("status") == "success":
                    self.send_response(201)
                else:
                    self.send_response(400)
                
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            
            # Process user input
            elif path == "/api/v1/menu/process":
                text = data.get("text", "")
                user_id = data.get("user_id", "")
                platform = data.get("platform", "")
                chat_id = data.get("chat_id", "")
                current_path = data.get("current_path", "/")
                state = data.get("state", {})
                
                if not text or not user_id or not platform:
                    self.send_error(400, "Missing required fields: text, user_id, platform")
                    return
                
                # Get user roles
                user_roles = []
                user_info = call_auth_api(f'/api/v1/auth/users/{user_id}', 'GET')
                if user_info.get("status") == "success":
                    user_roles = user_info.get("roles", [])
                
                # Try to match with menu commands
                submenu = menu_manager.get_submenu(current_path)
                
                # Find matching item
                matches = []
                for item in submenu.get("items", []):
                    # Match by text
                    if item.get("text") and text.lower() == item.get("text", "").lower():
                        matches.append({
                            "item": item,
                            "score": 1.0
                        })
                    
                    # Match by command
                    if item.get("type") == "command" and item.get("command") == text:
                        matches.append({
                            "item": item,
                            "score": 1.0
                        })
                    
                    # Match by path
                    if item.get("path") == text:
                        matches.append({
                            "item": item,
                            "score": 1.0
                        })
                
                # Find best match
                best_match = None
                if matches:
                    best_match = matches[0]
                
                # If no exact match, try fuzzy matching
                if not best_match:
                    for item in submenu.get("items", []):
                        if item.get("text") and text.lower() in item.get("text", "").lower():
                            matches.append({
                                "item": item,
                                "score": 0.5
                            })
                    
                    if matches:
                        best_match = max(matches, key=lambda x: x["score"])
                
                # Process match
                if best_match:
                    item = best_match["item"]
                    
                    # Check access
                    if not menu_manager.check_access(item, user_roles):
                        result = {
                            "status": "matched",
                            "action": "none",
                            "response_text": "❌ Доступ запрещён",
                            "error": "Access denied"
                        }
                    else:
                        # Navigate or execute
                        if item.get("type") == "menu":
                            # Navigate to submenu
                            navigate_result = navigation_manager.navigate(
                                user_id, platform, item.get("path", "/"), current_path
                            )
                            
                            result = {
                                "status": "matched",
                                "action": "navigate",
                                "path": item.get("path", "/"),
                                "response_text": f"📋 {item.get('text', 'Меню')}",
                                "new_menu": navigate_result.get("menu", {}),
                                "navigation": navigate_result
                            }
                        
                        elif item.get("type") == "command":
                            result = {
                                "status": "matched",
                                "action": "command",
                                "command": item.get("command", ""),
                                "response_text": f"✅ Выполняю: {item.get('text', 'Команда')}",
                                "path": current_path
                            }
                        
                        elif item.get("type") == "action":
                            # Execute action via core
                            action_result = call_core_api('/api/v1/modules/message', 'POST', {
                                "to": item.get("module", ""),
                                "command": item.get("action", ""),
                                "parameters": item.get("parameters", {})
                            })
                            
                            result = {
                                "status": "matched",
                                "action": "action",
                                "module": item.get("module", ""),
                                "action_name": item.get("action", ""),
                                "response_text": f"✅ Выполняю: {item.get('text', 'Действие')}",
                                "core_response": action_result
                            }
                        
                        else:
                            result = {
                                "status": "matched",
                                "action": "none",
                                "response_text": item.get("text", ""),
                                "path": current_path
                            }
                else:
                    # No match found - pass to LLM
                    result = {
                        "status": "not_matched",
                        "action": "none",
                        "response_text": "❓ Не распознано. Попробуйте выбрать из меню.",
                        "suggestions": [i.get("text") for i in submenu.get("items", [])[:5]]
                    }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())
            
            # Navigate
            elif path == "/api/v1/menu/navigate":
                user_id = data.get("user_id", "")
                platform = data.get("platform", "")
                menu_path = data.get("path", "/")
                from_path = data.get("from_path")
                
                if not user_id or not platform:
                    self.send_error(400, "Missing required fields: user_id, platform")
                    return
                
                result = navigation_manager.navigate(user_id, platform, menu_path, from_path)
                
                if result.get("status") == "success":
                    self.send_response(200)
                else:
                    self.send_response(400)
                
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())
            
            # Render menu
            elif path == "/api/v1/menu/render":
                menu_path = data.get("path", "/")
                platform = data.get("platform", CONFIG["default_platform"])
                user_id = data.get("user_id")
                chat_id = data.get("chat_id")
                
                result = menu_renderer.render(menu_path, platform, user_id)
                
                self.send_response(200 if result.get("status") == "success" else 400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())
            
            # Render inline keyboard
            elif path == "/api/v1/menu/render/inline":
                menu_path = data.get("path", "/")
                platform = data.get("platform", CONFIG["default_platform"])
                user_id = data.get("user_id")
                
                result = menu_renderer.render_inline(menu_path, platform, user_id)
                
                self.send_response(200 if result.get("status") == "success" else 400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())
            
            # Reorder items
            elif path == "/api/v1/menu/reorder":
                parent = data.get("parent", "/")
                order = data.get("order", [])
                
                result = menu_manager.reorder_items(parent, order)
                
                self.send_response(200 if result.get("status") == "success" else 400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            
            # Get accessible menu
            elif path == "/api/v1/menu/access/filter":
                user_id = data.get("user_id", "")
                user_roles = data.get("user_roles", [])
                platform = data.get("platform", CONFIG["default_platform"])
                
                if user_id:
                    user_info = call_auth_api(f'/api/v1/auth/users/{user_id}', 'GET')
                    if user_info.get("status") == "success":
                        user_roles = user_info.get("roles", user_roles)
                
                filtered_menu = menu_manager.filter_by_access(user_roles, platform)
                
                # Get accessible paths
                accessible_paths = []
                for path, item in filtered_menu.items():
                    if not path.startswith("metadata"):
                        accessible_paths.append(path)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "menu": filtered_menu,
                    "accessible_paths": accessible_paths,
                    "hidden_paths": [p for p in menu.keys() if p not in accessible_paths and not p.startswith("metadata")]
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
            
            # Update menu item
            if path.startswith("/api/v1/menu/"):
                menu_path = path[11:]  # Remove "/api/v1/menu/"
                
                result = menu_manager.update_item(menu_path, data)
                
                if result.get("status") == "success":
                    self.send_response(200)
                else:
                    self.send_response(404)
                
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            
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
            # Delete menu item
            if path.startswith("/api/v1/menu/"):
                menu_path = path[11:]  # Remove "/api/v1/menu/"
                
                if menu_path == "":
                    menu_path = "/"
                
                result = menu_manager.delete_item(menu_path)
                
                if result.get("status") == "success":
                    self.send_response(200)
                else:
                    self.send_response(404)
                
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling DELETE {path}: {e}")
            self.send_error(500, str(e))


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    sys.exit(0)


def main():
    """Main entry point"""
    global menu, menu_hash, menu_version
    
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot Menu Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Load configuration
    load_config()
    
    # Load menu
    menu, menu_hash = load_menu()
    menu_manager.menu = menu
    menu_version = menu.get("metadata", {}).get("version", "1.0.0")
    
    logger.info(f"Starting UniBot Menu Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    logger.info(f"Menu loaded: {len(menu)} items, version: {menu_version}")
    
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
        logger.info("Menu module stopped")


if __name__ == "__main__":
    main()
