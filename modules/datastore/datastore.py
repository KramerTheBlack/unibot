#!/usr/bin/env python3
"""
UniBot Datastore Module
Database connection and data storage module for UniBot
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import threading
import sqlite3
import logging
import logging.handlers
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

# Module metadata
MODULE_NAME = "datastore"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5002,
    "log_level": "INFO",
    "log_file": "/var/log/unibot/datastore.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "connection_timeout": 30,
    "query_timeout": 60,
    "max_retries": 3,
    "retry_delay": 1,
    "pool_enabled": True,
    "min_pool_size": 5,
    "max_pool_size": 20,
    "pool_timeout": 30,
    "cache_enabled": True,
    "cache_ttl": 300,
    "cache_max_size": 1000
}

# Global state
connections: Dict[str, Dict[str, Any]] = {}
connection_pool: Dict[str, List[Any]] = {}
pool_lock = threading.Lock()
query_cache: Dict[str, Tuple[Any, float]] = {}

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


# Database connectors
class DatabaseConnection:
    """Base database connection class"""
    
    def __init__(self, connection_id: str, config: dict):
        self.connection_id = connection_id
        self.config = config
        self.type = config.get("type", "unknown")
        self.last_used = None
        self.last_error = None
    
    def connect(self):
        """Establish connection to database"""
        raise NotImplementedError()
    
    def close(self):
        """Close connection"""
        pass
    
    def execute(self, query: str, parameters: dict = None) -> dict:
        """Execute query"""
        raise NotImplementedError()
    
    def get_tables(self) -> list:
        """Get list of tables"""
        raise NotImplementedError()
    
    def get_table_schema(self, table_name: str) -> dict:
        """Get table schema"""
        raise NotImplementedError()


class SQLiteConnection(DatabaseConnection):
    """SQLite database connection"""
    
    def __init__(self, connection_id: str, config: dict):
        super().__init__(connection_id, config)
        self.connection = None
    
    def connect(self):
        """Connect to SQLite database"""
        try:
            db_path = self.config.get("database", ":memory:")
            self.connection = sqlite3.connect(
                db_path,
                timeout=CONFIG["connection_timeout"]
            )
            self.connection.row_factory = sqlite3.Row
            self.last_used = datetime.utcnow()
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"SQLite connection error: {e}")
            return False
    
    def close(self):
        """Close connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def execute(self, query: str, parameters: dict = None) -> dict:
        """Execute query"""
        if not self.connection:
            if not self.connect():
                return {"status": "error", "error": self.last_error}
        
        try:
            cursor = self.connection.cursor()
            start_time = time.time()
            
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)
            
            execution_time = time.time() - start_time
            
            # Try to fetch results
            try:
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
                
                self.last_used = datetime.utcnow()
                return {
                    "status": "success",
                    "results": [dict(row) for row in rows],
                    "columns": columns,
                    "row_count": len(rows),
                    "execution_time": execution_time
                }
            except sqlite3.OperationalError:
                # No results to fetch (INSERT, UPDATE, DELETE)
                self.connection.commit()
                return {
                    "status": "success",
                    "results": [],
                    "columns": [],
                    "row_count": cursor.rowcount,
                    "execution_time": execution_time
                }
        
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"SQLite query error: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_tables(self) -> list:
        """Get list of tables"""
        result = self.execute(
            "SELECT name, type FROM sqlite_master WHERE type='table'"
        )
        if result["status"] == "success":
            return [{"name": row["name"], "type": row["type"]} for row in result["results"]]
        return []
    
    def get_table_schema(self, table_name: str) -> dict:
        """Get table schema"""
        result = self.execute(f"PRAGMA table_info({table_name})")
        if result["status"] == "success":
            columns = []
            for row in result["results"]:
                columns.append({
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": row["notnull"] == 0,
                    "default": row["dflt_value"],
                    "primary_key": row["pk"] == 1,
                    "auto_increment": False
                })
            return {
                "status": "success",
                "table": table_name,
                "columns": columns,
                "indexes": [],
                "foreign_keys": []
            }
        return {"status": "error", "error": result.get("error", "Table not found")}


class ConnectionManager:
    """Manage database connections"""
    
    def __init__(self):
        self.connections: Dict[str, DatabaseConnection] = {}
        self.connection_configs: Dict[str, dict] = {}
        self.lock = threading.Lock()
    
    def create_connection(self, connection_id: str, config: dict) -> dict:
        """Create a new database connection"""
        with self.lock:
            if connection_id in self.connections:
                return {"status": "error", "message": f"Connection {connection_id} already exists"}
            
            # Store config
            self.connection_configs[connection_id] = config
            
            # Create appropriate connection type
            conn_type = config.get("type", "sqlite").lower()
            
            if conn_type == "sqlite":
                connection = SQLiteConnection(connection_id, config)
            else:
                # For other types, use SQLite as fallback for now
                logger.warning(f"Connection type {conn_type} not fully implemented, using SQLite")
                connection = SQLiteConnection(connection_id, config)
            
            self.connections[connection_id] = connection
            
            # Try to connect
            if connection.connect():
                logger.info(f"Connection {connection_id} created ({conn_type})")
                return {
                    "status": "success",
                    "connection_id": connection_id,
                    "message": f"Connection {connection_id} created"
                }
            else:
                del self.connections[connection_id]
                del self.connection_configs[connection_id]
                return {
                    "status": "error",
                    "message": f"Failed to create connection: {connection.last_error}"
                }
    
    def get_connection(self, connection_id: str) -> Optional[DatabaseConnection]:
        """Get connection by ID"""
        with self.lock:
            return self.connections.get(connection_id)
    
    def get_connection_config(self, connection_id: str) -> Optional[dict]:
        """Get connection configuration"""
        with self.lock:
            return self.connection_configs.get(connection_id)
    
    def delete_connection(self, connection_id: str) -> dict:
        """Delete connection"""
        with self.lock:
            if connection_id in self.connections:
                connection = self.connections[connection_id]
                connection.close()
                del self.connections[connection_id]
                del self.connection_configs[connection_id]
                logger.info(f"Connection {connection_id} deleted")
                return {"status": "success", "message": f"Connection {connection_id} deleted"}
            return {"status": "error", "message": f"Connection {connection_id} not found"}
    
    def list_connections(self) -> list:
        """List all connections"""
        with self.lock:
            connection_list = []
            for conn_id, connection in self.connections.items():
                config = self.connection_configs.get(conn_id, {})
                connection_list.append({
                    "connection_id": conn_id,
                    "name": config.get("name", conn_id),
                    "type": config.get("type", "unknown"),
                    "status": "active" if connection.connection else "inactive",
                    "created_at": config.get("created_at", ""),
                    "last_used": connection.last_used.isoformat() + "Z" if connection.last_used else None
                })
            return connection_list
    
    def test_connection(self, connection_id: str) -> dict:
        """Test database connection"""
        connection = self.get_connection(connection_id)
        if not connection:
            return {"status": "error", "message": f"Connection {connection_id} not found"}
        
        start_time = time.time()
        
        # Try to connect and run a simple query
        if connection.connect():
            # Try to get tables
            tables = connection.get_tables()
            execution_time = time.time() - start_time
            
            return {
                "status": "success",
                "message": f"Connection test successful",
                "latency": execution_time,
                "details": {
                    "tables": len(tables),
                    "type": connection.type
                }
            }
        else:
            return {
                "status": "error",
                "message": f"Connection test failed: {connection.last_error}"
            }


# Global connection manager
connection_manager = ConnectionManager()


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for datastore module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            # List connections
            if path == "/api/v1/connections":
                connections = connection_manager.list_connections()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "connections": connections,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get connection details
            elif path.startswith("/api/v1/connections/"):
                parts = path.split("/")
                conn_id = parts[3]
                
                if len(parts) == 4:
                    # Get connection details
                    config = connection_manager.get_connection_config(conn_id)
                    connection = connection_manager.get_connection(conn_id)
                    
                    if config:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "connection_id": conn_id,
                            "name": config.get("name", conn_id),
                            "type": config.get("type", "unknown"),
                            "config": {k: v for k, v in config.items() if k != "password"},
                            "status": "active" if connection and connection.connection else "inactive",
                            "last_used": connection.last_used.isoformat() + "Z" if connection and connection.last_used else None,
                            "last_error": connection.last_error if connection else None
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                    else:
                        self.send_error(404, f"Connection {conn_id} not found")
                
                elif len(parts) >= 5:
                    # Handle /connections/{id}/tables or /connections/{id}/tables/{table}
                    if parts[4] == "tables":
                        connection = connection_manager.get_connection(conn_id)
                        if connection:
                            if len(parts) == 5:
                                # List tables
                                tables = connection.get_tables()
                                self.send_response(200)
                                self.send_header("Content-Type", "application/json")
                                self.end_headers()
                                response = {
                                    "status": "success",
                                    "tables": tables
                                }
                                self.wfile.write(json.dumps(response, indent=2).encode())
                            elif len(parts) >= 7 and parts[5] == "schema":
                                # Get table schema
                                table_name = parts[6]
                                schema = connection.get_table_schema(table_name)
                                self.send_response(200)
                                self.send_header("Content-Type", "application/json")
                                self.end_headers()
                                self.wfile.write(json.dumps(schema, indent=2).encode())
                            else:
                                self.send_error(404, "Not found")
                        else:
                            self.send_error(404, f"Connection {conn_id} not found")
                    else:
                        self.send_error(404, "Not found")
                else:
                    self.send_error(404, "Not found")
            
            # Health check
            elif path == "/api/v1/health":
                connections = connection_manager.list_connections()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "connections": connections,
                    "active_connections": len([c for c in connections if c["status"] == "active"]),
                    "query_cache_size": len(query_cache),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Cache stats
            elif path == "/api/v1/cache/stats":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "hits": 0,  # Would track in real implementation
                    "misses": 0,
                    "hit_rate": 0.0,
                    "size": len(query_cache),
                    "max_size": CONFIG["cache_max_size"]
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
            
            # Create connection
            if path == "/api/v1/connections":
                required = ["name", "type"]
                if all(k in data for k in required):
                    connection_id = str(uuid.uuid4())
                    config = {
                        "name": data["name"],
                        "type": data["type"],
                        "connection_string": data.get("connection_string", ""),
                        "host": data.get("host", ""),
                        "port": data.get("port", 0),
                        "database": data.get("database", ""),
                        "username": data.get("username", ""),
                        "password": data.get("password", ""),
                        "ssl_enabled": data.get("ssl_enabled", False),
                        "options": data.get("options", {}),
                        "created_at": datetime.utcnow().isoformat() + "Z"
                    }
                    
                    result = connection_manager.create_connection(connection_id, config)
                    
                    if result["status"] == "success":
                        self.send_response(201)
                    else:
                        self.send_response(400)
                    
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    result["connection_id"] = connection_id
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_error(400, "Missing required fields: name, type")
            
            # Test connection
            elif path.startswith("/api/v1/connections/"):
                parts = path.split("/")
                conn_id = parts[3]
                
                if len(parts) >= 5 and parts[4] == "test":
                    result = connection_manager.test_connection(conn_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                
                elif len(parts) >= 5 and parts[4] == "query":
                    # Execute query
                    connection = connection_manager.get_connection(conn_id)
                    if connection:
                        query = data.get("query", "")
                        parameters = data.get("parameters", {})
                        
                        result = connection.execute(query, parameters)
                        
                        if result["status"] == "success":
                            self.send_response(200)
                        else:
                            self.send_response(400)
                        
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode())
                    else:
                        self.send_error(404, f"Connection {conn_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "tables":
                    # Create table
                    connection = connection_manager.get_connection(conn_id)
                    if connection:
                        table_name = parts[5] if len(parts) >= 6 else ""
                        
                        if table_name and len(parts) == 6:
                            # Create table
                            columns = data.get("columns", [])
                            
                            # Build CREATE TABLE query
                            column_defs = []
                            for col in columns:
                                col_def = f'{col["name"]} {col.get("type", "TEXT")}'
                                if col.get("primary_key"):
                                    col_def += " PRIMARY KEY"
                                if col.get("auto_increment"):
                                    col_def += " AUTOINCREMENT"
                                if not col.get("nullable", True):
                                    col_def += " NOT NULL"
                                if "default" in col:
                                    col_def += f" DEFAULT {col['default']}"
                                column_defs.append(col_def)
                            
                            query = f"CREATE TABLE {table_name} ({', '.join(column_defs)})"
                            
                            result = connection.execute(query)
                            self.send_response(200 if result["status"] == "success" else 400)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps(result).encode())
                    else:
                        self.send_error(404, f"Connection {conn_id} not found")
            
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
            
            # Update connection
            if path.startswith("/api/v1/connections/"):
                parts = path.split("/")
                conn_id = parts[3]
                
                if len(parts) == 4:
                    config = connection_manager.get_connection_config(conn_id)
                    if config:
                        # Update config
                        for key, value in data.items():
                            if key != "connection_id":
                                config[key] = value
                        
                        # Reconnect with new config
                        connection_manager.delete_connection(conn_id)
                        result = connection_manager.create_connection(conn_id, config)
                        
                        self.send_response(200 if result["status"] == "success" else 400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode())
                    else:
                        self.send_error(404, f"Connection {conn_id} not found")
            
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
            # Delete connection
            if path.startswith("/api/v1/connections/"):
                parts = path.split("/")
                conn_id = parts[3]
                
                if len(parts) == 4:
                    result = connection_manager.delete_connection(conn_id)
                    self.send_response(200 if result["status"] == "success" else 404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                
                elif len(parts) >= 6 and parts[4] == "tables":
                    # Delete table
                    conn_id = parts[3]
                    table_name = parts[5]
                    connection = connection_manager.get_connection(conn_id)
                    
                    if connection:
                        result = connection.execute(f"DROP TABLE {table_name}")
                        self.send_response(200 if result["status"] == "success" else 400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode())
                    else:
                        self.send_error(404, f"Connection {conn_id} not found")
            
            # Clear cache
            elif path == "/api/v1/cache/clear":
                global query_cache
                query_cache = {}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {"status": "success", "cleared_count": 0}
                self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_error(404, "Not found")
        
        except Exception as e:
            logger.error(f"Error handling DELETE {path}: {e}")
            self.send_error(500, str(e))


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    # Close all connections
    for conn_id, connection in connection_manager.connections.items():
        connection.close()
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot Datastore Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Load configuration
    load_config()
    
    logger.info(f"Starting UniBot Datastore Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    
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
        logger.info("Datastore module stopped")


if __name__ == "__main__":
    main()
