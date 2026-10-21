#!/usr/bin/env python3
"""
UniBot Core Module
Central module for managing inter-module communication
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
from typing import Dict, Any, Optional, Tuple
import socket
import signal

# Module metadata
MODULE_NAME = "core"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5000,
    "thread_pool_size": 10,
    "max_queue_size": 1000,
    "cache_ttl": 3600,
    "timeout": 30,
    "retry_attempts": 3,
    "log_level": "INFO",
    "log_file": "/var/log/unibot/core.log",
    "log_max_size": 10485760,
    "log_backup_count": 5
}

# Global state
modules: Dict[str, Dict[str, Any]] = {}
message_queue: queue.Queue = queue.Queue(maxsize=CONFIG["max_queue_size"])
cache: Dict[str, Tuple[Any, float]] = {}
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


class MessageQueue:
    """Thread-safe message queue for inter-module communication"""
    
    def __init__(self, max_size: int = 1000):
        self.queue = queue.Queue(maxsize=max_size)
        self.metrics = {
            "messages_queued": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "queue_depth": 0
        }
        self.metrics_lock = threading.Lock()
    
    def put(self, message: Dict[str, Any]) -> bool:
        """Add message to queue"""
        try:
            self.queue.put(message, timeout=5)
            with self.metrics_lock:
                self.metrics["messages_queued"] += 1
                self.metrics["queue_depth"] = self.queue.qsize()
            return True
        except queue.Full:
            with self.metrics_lock:
                self.metrics["messages_failed"] += 1
            logger.error(f"Queue full, message dropped: {message.get('request_id', 'N/A')}")
            return False
    
    def get(self) -> Optional[Dict[str, Any]]:
        """Get message from queue"""
        try:
            message = self.queue.get(timeout=1)
            with self.metrics_lock:
                self.metrics["messages_processed"] += 1
                self.metrics["queue_depth"] = self.queue.qsize()
            return message
        except queue.Empty:
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get queue metrics"""
        with self.metrics_lock:
            return dict(self.metrics)


class Cache:
    """Simple in-memory cache with TTL"""
    
    def __init__(self, default_ttl: int = 3600):
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl
        self.lock = threading.Lock()
        self.metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_size": 0
        }
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set cache value"""
        with self.lock:
            expires = time.time() + (ttl if ttl is not None else self.default_ttl)
            self.cache[key] = (value, expires)
            self.metrics["cache_size"] = len(self.cache)
        return True
    
    def get(self, key: str) -> Optional[Any]:
        """Get cache value"""
        with self.lock:
            if key in self.cache:
                value, expires = self.cache[key]
                if expires > time.time():
                    self.metrics["cache_hits"] += 1
                    return value
                else:
                    # Expired, remove it
                    del self.cache[key]
                    self.metrics["cache_size"] = len(self.cache)
            self.metrics["cache_misses"] += 1
        return None
    
    def delete(self, key: str) -> bool:
        """Delete cache value"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                self.metrics["cache_size"] = len(self.cache)
                return True
        return False
    
    def cleanup(self):
        """Cleanup expired entries"""
        with self.lock:
            now = time.time()
            expired_keys = [k for k, (_, expires) in self.cache.items() if expires <= now]
            for key in expired_keys:
                del self.cache[key]
            self.metrics["cache_size"] = len(self.cache)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics"""
        return dict(self.metrics)


class ModuleManager:
    """Manage module registration and communication"""
    
    def __init__(self):
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.check_interval = 60
    
    def register(self, module_name: str, version: str, endpoints: list, host: str, port: int) -> Dict[str, Any]:
        """Register a new module"""
        with self.lock:
            if module_name in self.modules:
                logger.warning(f"Module {module_name} already registered, updating...")
            
            self.modules[module_name] = {
                "name": module_name,
                "version": version,
                "endpoints": endpoints,
                "host": host,
                "port": port,
                "status": "active",
                "last_ping": datetime.utcnow().isoformat() + "Z",
                "registered_at": datetime.utcnow().isoformat() + "Z"
            }
            
            logger.info(f"Module registered: {module_name} v{version} at {host}:{port}")
            return {
                "status": "success",
                "module_id": module_name,
                "message": f"Module {module_name} registered successfully"
            }
    
    def unregister(self, module_name: str) -> Dict[str, Any]:
        """Unregister a module"""
        with self.lock:
            if module_name in self.modules:
                del self.modules[module_name]
                logger.info(f"Module unregistered: {module_name}")
                return {
                    "status": "success",
                    "message": f"Module {module_name} unregistered"
                }
            return {
                "status": "error",
                "message": f"Module {module_name} not found"
            }
    
    def get_module(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Get module information"""
        with self.lock:
            return self.modules.get(module_name)
    
    def get_all_modules(self) -> list:
        """Get all registered modules"""
        with self.lock:
            return list(self.modules.values())
    
    def check_health(self):
        """Check health of all modules"""
        with self.lock:
            for name, module in self.modules.items():
                # In real implementation, this would ping the module
                module["status"] = "active"
                module["last_ping"] = datetime.utcnow().isoformat() + "Z"


# Global instances
msg_queue = MessageQueue(max_size=CONFIG["max_queue_size"])
cache = Cache(default_ttl=CONFIG["cache_ttl"])
module_manager = ModuleManager()


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for core module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            if path == "/api/v1/modules":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "modules": module_manager.get_all_modules(),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path.startswith("/api/v1/modules/"):
                parts = path.split("/")
                if len(parts) >= 5 and parts[4] == "status":
                    module_name = parts[3]
                    module = module_manager.get_module(module_name)
                    if module:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(module).encode())
                    else:
                        self.send_error(404, f"Module {module_name} not found")
                else:
                    self.send_error(404, "Not found")
            
            elif path == "/api/v1/queue/metrics":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(msg_queue.get_metrics()).encode())
            
            elif path == "/api/v1/cache/metrics":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(cache.get_metrics()).encode())
            
            elif path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "modules": [m["name"] for m in module_manager.get_all_modules()],
                    "queue_size": msg_queue.get_metrics()["queue_depth"],
                    "cache_size": cache.get_metrics()["cache_size"],
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            elif path == "/api/v1/metrics":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "queue_metrics": msg_queue.get_metrics(),
                    "cache_metrics": cache.get_metrics(),
                    "module_count": len(module_manager.get_all_modules())
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
            
            if path == "/api/v1/modules/register":
                required = ["module_name", "version", "endpoints"]
                if all(k in data for k in required):
                    host = data.get("host", "localhost")
                    port = data.get("port", 5001)
                    response = module_manager.register(
                        data["module_name"],
                        data["version"],
                        data["endpoints"],
                        host,
                        port
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_error(400, "Missing required fields: module_name, version, endpoints")
            
            elif path.startswith("/api/v1/modules/"):
                parts = path.split("/")
                if len(parts) >= 5 and parts[4] == "message":
                    module_name = parts[3]
                    module = module_manager.get_module(module_name)
                    if module:
                        # Create message
                        message = {
                            "from": MODULE_NAME,
                            "to": module_name,
                            "command": data.get("command", ""),
                            "parameters": data.get("parameters", {}),
                            "request_id": str(uuid.uuid4()),
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "priority": data.get("priority", "normal"),
                            "retry_count": 0
                        }
                        
                        # Queue message
                        if msg_queue.put(message):
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "status": "queued",
                                "request_id": message["request_id"],
                                "module": module_name
                            }
                            self.wfile.write(json.dumps(response).encode())
                        else:
                            self.send_error(503, "Queue full")
                    else:
                        self.send_error(404, f"Module {module_name} not found")
                else:
                    self.send_error(404, "Not found")
            
            elif path == "/api/v1/queue/send":
                required = ["module_name", "command"]
                if all(k in data for k in required):
                    message = {
                        "from": MODULE_NAME,
                        "to": data["module_name"],
                        "command": data["command"],
                        "parameters": data.get("parameters", {}),
                        "request_id": str(uuid.uuid4()),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "priority": data.get("priority", "normal"),
                        "retry_count": 0
                    }
                    
                    if msg_queue.put(message):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "queue_id": message["request_id"],
                            "status": "queued"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(503, "Queue full")
                else:
                    self.send_error(400, "Missing required fields: module_name, command")
            
            elif path == "/api/v1/cache/set":
                required = ["key", "value"]
                if all(k in data for k in required):
                    cache.set(
                        data["key"],
                        data["value"],
                        data.get("ttl")
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "success",
                        "key": data["key"]
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_error(400, "Missing required fields: key, value")
            
            elif path == "/api/v1/log":
                log_level = data.get("level", "INFO").upper()
                module = data.get("module", "unknown")
                message = data.get("message", "")
                context = data.get("context", {})
                
                logger.log(
                    getattr(logging, log_level, logging.INFO),
                    f"[{module}] {message} - {json.dumps(context)}"
                )
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "log_id": str(uuid.uuid4())
                }
                self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling POST {path}: {e}")
            self.send_error(500, str(e))
    
    def do_GET_caches(self):
        """Handle GET requests for cache"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith("/api/v1/cache/get/"):
            parts = path.split("/")
            if len(parts) >= 6:
                key = parts[5]
                value = cache.get(key)
                if value is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "found",
                        "key": key,
                        "value": value
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {
                        "status": "not_found",
                        "key": key
                    }
                    self.wfile.write(json.dumps(response).encode())
        else:
            self.send_error(404, "Not found")


def process_messages():
    """Background thread to process queued messages"""
    logger.info("Message processor started")
    
    while True:
        try:
            message = msg_queue.get()
            if message:
                # Process message
                module_name = message.get("to")
                module = module_manager.get_module(module_name)
                
                if module:
                    logger.info(f"Processing message {message.get('request_id')} to {module_name}")
                    # In real implementation, this would send to the module
                    # For now, just log it
                    logger.debug(f"Message content: {json.dumps(message, indent=2)}")
                else:
                    logger.warning(f"Module {module_name} not found for message {message.get('request_id')}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
        
        time.sleep(0.1)


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    sys.exit(0)


def main():
    """Main entry point"""
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="UniBot Core Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Register self as a module
    module_manager.register(
        MODULE_NAME,
        MODULE_VERSION,
        ["/api/v1/modules", "/api/v1/queue", "/api/v1/cache", "/api/v1/health", "/api/v1/log"],
        CONFIG["listen_address"],
        CONFIG["listen_port"]
    )
    
    logger.info(f"Starting UniBot Core Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    
    # Start message processor thread
    processor_thread = threading.Thread(target=process_messages, daemon=True)
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
        logger.info("Core module stopped")


if __name__ == "__main__":
    main()
