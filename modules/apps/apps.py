#!/usr/bin/env python3
"""
UniBot Apps Module
Dynamic functional module loader
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import threading
import importlib
import logging
import logging.handlers
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Module metadata
MODULE_NAME = "apps"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5006,
    "apps_dir": "/app",
    "log_level": "INFO",
    "log_file": "/var/log/unibot/apps.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "module_timeout": 30
}

# Global state
loaded_apps = {}
lock = threading.Lock()

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


class AppManager:
    """Manage dynamic loading of functional apps"""
    
    def __init__(self, apps_dir):
        self.apps_dir = apps_dir
        self.loaded_apps = {}
        self.lock = threading.Lock()
    
    def discover_apps(self):
        """Discover all available apps in the apps directory"""
        apps = []
        if os.path.exists(self.apps_dir):
            for item in os.listdir(self.apps_dir):
                app_path = os.path.join(self.apps_dir, item)
                if os.path.isdir(app_path):
                    module_file = os.path.join(app_path, "module.yml")
                    if os.path.exists(module_file):
                        apps.append(item)
        return apps
    
    def load_app(self, app_name):
        """Load a specific app module"""
        with self.lock:
            if app_name in self.loaded_apps:
                logger.info(f"App {app_name} already loaded")
                return self.loaded_apps[app_name]
            
            app_path = os.path.join(self.apps_dir, app_name)
            
            try:
                # Read module metadata
                module_yml = os.path.join(app_path, "module.yml")
                module_conf = os.path.join(app_path, "module.conf")
                module_api = os.path.join(app_path, "module.api")
                module_py = os.path.join(app_path, f"{app_name}.py")
                
                # Parse module.yml
                app_info = {
                    "name": app_name,
                    "version": "1.0.0",
                    "description": "",
                    "enabled": True,
                    "config": {},
                    "api": {},
                    "module_path": app_path
                }
                
                if os.path.exists(module_yml):
                    try:
                        import yaml
                        with open(module_yml, 'r') as f:
                            yml_data = yaml.safe_load(f)
                        if yml_data:
                            app_info.update(yml_data)
                    except Exception as e:
                        logger.warning(f"Could not parse {module_yml}: {e}")
                
                # Parse module.conf
                if os.path.exists(module_conf):
                    try:
                        import configparser
                        config = configparser.ConfigParser()
                        config.read(module_conf)
                        app_info["config"] = {s: dict(config.items(s)) for s in config.sections()}
                    except Exception as e:
                        logger.warning(f"Could not parse {module_conf}: {e}")
                
                # Parse module.api
                if os.path.exists(module_api):
                    try:
                        with open(module_api, 'r') as f:
                            app_info["api"] = json.load(f)
                    except Exception as e:
                        logger.warning(f"Could not parse {module_api}: {e}")
                
                # Try to load the Python module
                if os.path.exists(module_py):
                    try:
                        spec = importlib.util.spec_from_file_location(
                            f"app_{app_name}",
                            module_py
                        )
                        if spec and spec.loader:
                            app_module = importlib.util.module_from_spec(spec)
                            sys.modules[f"app_{app_name}"] = app_module
                            spec.loader.exec_module(app_module)
                            app_info["module"] = app_module
                            app_info["loaded"] = True
                        else:
                            app_info["loaded"] = False
                    except Exception as e:
                        logger.warning(f"Could not load {module_py}: {e}")
                        app_info["loaded"] = False
                else:
                    logger.info(f"No Python file found for {app_name}")
                    app_info["loaded"] = False
                
                self.loaded_apps[app_name] = app_info
                logger.info(f"Loaded app: {app_name} v{app_info.get('version', 'unknown')}")
                
                return app_info
                
            except Exception as e:
                logger.error(f"Error loading app {app_name}: {e}")
                return None
    
    def load_all(self):
        """Load all discovered apps"""
        apps = self.discover_apps()
        results = {}
        for app_name in apps:
            app_info = self.load_app(app_name)
            if app_info:
                results[app_name] = app_info
        return results
    
    def unload_app(self, app_name):
        """Unload an app"""
        with self.lock:
            if app_name in self.loaded_apps:
                del self.loaded_apps[app_name]
                logger.info(f"Unloaded app: {app_name}")
                return True
            return False
    
    def get_app(self, app_name):
        """Get app information"""
        with self.lock:
            return self.loaded_apps.get(app_name)
    
    def get_all_apps(self):
        """Get all loaded apps"""
        with self.lock:
            return list(self.loaded_apps.values())
    
    def call_app(self, app_name, command, params=None):
        """Call a function in an app"""
        app = self.get_app(app_name)
        if not app or not app.get("loaded"):
            return {"status": "error", "message": f"App {app_name} not loaded"}
        
        module = app.get("module")
        if not module:
            return {"status": "error", "message": f"App {app_name} has no module"}
        
        try:
            # Try to find and call the command
            if hasattr(module, command):
                func = getattr(module, command)
                result = func(params or {})
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": f"Command {command} not found in {app_name}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Global app manager
app_manager = AppManager(CONFIG["apps_dir"])


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for apps module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            if path == "/api/v1/apps":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "apps": app_manager.get_all_apps(),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path.startswith("/api/v1/apps/"):
                parts = path.split("/")
                if len(parts) >= 5:
                    app_name = parts[4]
                    app = app_manager.get_app(app_name)
                    if app:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(app).encode())
                    else:
                        self.send_error(404, f"App {app_name} not found")
                else:
                    self.send_error(404, "Not found")
            
            elif path == "/api/v1/apps/load":
                apps = app_manager.discover_apps()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "discovered": apps,
                    "loaded": list(loaded_apps.keys())
                }
                self.wfile.write(json.dumps(response).encode())
            
            elif path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "apps_loaded": len(app_manager.get_all_apps()),
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
            
            if path == "/api/v1/apps/load":
                app_name = data.get("app_name")
                if app_name:
                    app_info = app_manager.load_app(app_name)
                    if app_info:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "success", "app": app_name}).encode())
                    else:
                        self.send_error(400, f"Could not load app {app_name}")
                else:
                    # Load all
                    apps = app_manager.load_all()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "loaded": list(apps.keys())}).encode())
            
            elif path.startswith("/api/v1/apps/"):
                parts = path.split("/")
                if len(parts) >= 5 and parts[4] == "unload":
                    app_name = parts[3]
                    if app_manager.unload_app(app_name):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "success", "app": app_name}).encode())
                    else:
                        self.send_error(404, f"App {app_name} not found")
                elif len(parts) >= 5 and parts[4] == "call":
                    app_name = parts[3]
                    command = data.get("command")
                    params = data.get("parameters", {})
                    result = app_manager.call_app(app_name, command, params)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_error(404, "Not found")
            
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
    
    parser = argparse.ArgumentParser(description="UniBot Apps Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--apps-dir", type=str, default=CONFIG["apps_dir"], help="Directory to load apps from")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    CONFIG["apps_dir"] = args.apps_dir
    
    # Update app manager with new apps_dir
    global app_manager
    app_manager = AppManager(args.apps_dir)
    
    logger.info(f"Starting UniBot Apps Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    logger.info(f"Apps directory: {args.apps_dir}")
    
    # Load all apps at startup
    discovered = app_manager.discover_apps()
    logger.info(f"Discovered apps: {discovered}")
    loaded = app_manager.load_all()
    logger.info(f"Loaded {len(loaded)} apps")
    
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
        logger.info("Apps module stopped")


if __name__ == "__main__":
    main()
