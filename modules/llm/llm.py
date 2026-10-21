#!/usr/bin/env python3
"""
UniBot LLM Module
Large Language Model integration module for UniBot
Version: 2026.10.21_1
"""

import os
import sys
import json
import uuid
import time
import threading
import queue
import re
import logging
import logging.handlers
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Tuple

# Module metadata
MODULE_NAME = "llm"
MODULE_VERSION = "2026.10.21_1"

# Configuration
CONFIG = {
    "listen_address": "0.0.0.0",
    "listen_port": 5004,
    "default_provider": "openai",
    "default_model": "gpt-4",
    "max_tokens": 4096,
    "temperature": 0.7,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "sanitize_input": True,
    "sanitize_output": True,
    "content_filter_enabled": True,
    "anonymize_user_data": True,
    "store_conversations": False,
    "log_prompts": False,
    "timeout": 30,
    "retry_attempts": 3,
    "max_requests_per_minute": 60,
    "max_tokens_per_minute": 60000,
    "burst_limit": 10,
    "log_level": "INFO",
    "log_file": "/var/log/unibot/llm.log",
    "log_max_size": 10485760,
    "log_backup_count": 5,
    "auth_endpoint": "http://auth:5001"
}

# Global state
providers: Dict[str, Dict[str, Any]] = {}
models: Dict[str, Dict[str, Any]] = {}
conversations: Dict[str, Dict[str, Any]] = {}
prompts: Dict[str, Dict[str, Any]] = {}
rate_limits: Dict[str, Dict[str, Any]] = {}
usage_stats: Dict[str, Any] = {
    "total_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_requests": 0,
    "by_model": {},
    "by_day": {}
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
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                    elif ',' in value:
                        value = [x.strip() for x in value.split(',')]
                    
                    CONFIG[full_key] = value


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


def sanitize_text(text: str, level: str = "medium") -> str:
    """Sanitize text based on level"""
    # Basic sanitization
    if level in ["low", "medium", "high"]:
        # Remove potential harmful content
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)  # Remove control characters
        
        # For high level, also check for common patterns
        if level == "high":
            # Remove SQL injection patterns
            text = re.sub(r'(--|;|\/\*|\*\/|xp_)', '', text, flags=re.IGNORECASE)
            # Remove script tags
            text = re.sub(r'(<script|javascript:)', '', text, flags=re.IGNORECASE)
    
    return text


def anonymize_text(text: str) -> str:
    """Anonymize sensitive information in text"""
    # Replace phone numbers
    text = re.sub(r'\+?[\d\s\-()]{10,}', '[PHONE]', text)
    # Replace emails
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]', text)
    # Replace URLs
    text = re.sub(r'https?://[^\s]+', '[URL]', text)
    # Replace IPs
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', text)
    
    return text


def moderate_content(text: str) -> Tuple[bool, dict]:
    """Moderate content and check for harmful material"""
    # Simple moderation - in real implementation, would call an LLM or dedicated service
    
    # Check for common harmful patterns
    harmful_patterns = [
        (r'(hate|racism|racist|nazi|kkk)', 'hate'),
        (r'(kill|murder|suicide|self[- ]harm)', 'self_harm'),
        (r'(rape|sexual[ -]assault|pedo)', 'sexual'),
        (r'(bomb|terror|terrorism|blast)', 'violence'),
        (r'(fuck|cunt|bitch|whore|dick|pussy)', 'profanity'),
    ]
    
    categories = {
        "hate": {"flagged": False, "score": 0.0},
        "harassment": {"flagged": False, "score": 0.0},
        "self_harm": {"flagged": False, "score": 0.0},
        "sexual": {"flagged": False, "score": 0.0},
        "violence": {"flagged": False, "score": 0.0},
        "profanity": {"flagged": False, "score": 0.0}
    }
    
    text_lower = text.lower()
    for pattern, category in harmful_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            categories[category]["flagged"] = True
            categories[category]["score"] = 1.0
    
    is_safe = not any(c["flagged"] for c in categories.values())
    is_flagged = not is_safe
    
    return is_safe, {
        "safe": is_safe,
        "flagged": is_flagged,
        "categories": categories,
        "recommendation": "allow" if is_safe else "warn",
        "explanation": "Passed basic moderation" if is_safe else "Flagged by pattern matching"
    }


# Provider classes
class LLMProvider:
    """Base class for LLM providers"""
    
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.models: Dict[str, dict] = {}
        self.enabled = True
    
    def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> dict:
        """Generate text from prompt"""
        raise NotImplementedError()
    
    def chat(self, messages: list, **kwargs) -> dict:
        """Generate chat completion"""
        raise NotImplementedError()
    
    def embed(self, text: str, **kwargs) -> dict:
        """Generate embeddings"""
        raise NotImplementedError()
    
    def list_models(self) -> list:
        """List available models"""
        return list(self.models.values())


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation"""
    
    def __init__(self):
        super().__init__("openai")
        self.api_url = CONFIG.get("openai_api_url", "https://api.openai.com/v1")
        self.api_key = CONFIG.get("openai_api_key", "")
        self.models = {
            "gpt-4": {
                "id": "gpt-4",
                "name": "GPT-4",
                "provider": "openai",
                "description": "OpenAI's most advanced model",
                "max_tokens": 8192,
                "pricing": {"prompt": 0.03, "completion": 0.06},
                "supported": True,
                "default": False
            },
            "gpt-4-32k": {
                "id": "gpt-4-32k",
                "name": "GPT-4 32K",
                "provider": "openai",
                "description": "GPT-4 with 32K context",
                "max_tokens": 32768,
                "pricing": {"prompt": 0.06, "completion": 0.12},
                "supported": True,
                "default": False
            },
            "gpt-4-turbo": {
                "id": "gpt-4-turbo",
                "name": "GPT-4 Turbo",
                "provider": "openai",
                "description": "Faster and cheaper GPT-4",
                "max_tokens": 8192,
                "pricing": {"prompt": 0.01, "completion": 0.03},
                "supported": True,
                "default": True
            },
            "gpt-3.5-turbo": {
                "id": "gpt-3.5-turbo",
                "name": "GPT-3.5 Turbo",
                "provider": "openai",
                "description": "OpenAI's fast and cost-effective model",
                "max_tokens": 4096,
                "pricing": {"prompt": 0.0015, "completion": 0.002},
                "supported": True,
                "default": False
            }
        }
    
    def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> dict:
        """Generate text using OpenAI API"""
        import requests
        
        # Sanitize input
        if CONFIG["sanitize_input"]:
            prompt = sanitize_text(prompt)
            if system_prompt:
                system_prompt = sanitize_text(system_prompt)
        
        # Anonymize if needed
        if CONFIG["anonymize_user_data"]:
            prompt = anonymize_text(prompt)
            if system_prompt:
                system_prompt = anonymize_text(system_prompt)
        
        # Moderate content
        if CONFIG["content_filter_enabled"]:
            is_safe, moderation = moderate_content(prompt)
            if not is_safe:
                return {
                    "status": "error",
                    "error": "Content blocked by moderation",
                    "moderation": moderation
                }
        
        # Prepare request
        model = kwargs.get("model", CONFIG["default_model"])
        max_tokens = kwargs.get("max_tokens", CONFIG["max_tokens"])
        temperature = kwargs.get("temperature", CONFIG["temperature"])
        
        # In real implementation, would call actual API
        # For demo, generate a mock response
        logger.info(f"OpenAI: Generate with {model}, max_tokens={max_tokens}, temperature={temperature}")
        
        # Simulate token usage
        prompt_tokens = len(prompt.split())
        completion_tokens = 50  # Mock response
        
        # Update stats
        with threading.Lock():
            usage_stats["total_tokens"] += prompt_tokens + completion_tokens
            usage_stats["prompt_tokens"] += prompt_tokens
            usage_stats["completion_tokens"] += completion_tokens
            usage_stats["total_requests"] += 1
            if model not in usage_stats["by_model"]:
                usage_stats["by_model"][model] = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
            usage_stats["by_model"][model]["prompt_tokens"] += prompt_tokens
            usage_stats["by_model"][model]["completion_tokens"] += completion_tokens
            usage_stats["by_model"][model]["requests"] += 1
        
        # Generate mock response
        mock_response = f"This is a mock response from {model}. Your prompt was: {prompt[:100]}..."
        
        return {
            "status": "success",
            "text": mock_response,
            "model": model,
            "provider": "openai",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            },
            "latency": 0.5,
            "finish_reason": "stop"
        }
    
    def chat(self, messages: list, **kwargs) -> dict:
        """Generate chat completion"""
        # For demo, convert to prompt
        prompt = "\n\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in messages])
        prompt += "\n\nassistant:"
        
        result = self.generate(prompt, **kwargs)
        
        if result["status"] == "success":
            return {
                "status": "success",
                "message": {
                    "role": "assistant",
                    "content": result["text"],
                    "finish_reason": result.get("finish_reason", "stop")
                },
                "model": result["model"],
                "usage": result["usage"],
                "latency": result["latency"]
            }
        else:
            return result


class YandexProvider(LLMProvider):
    """Yandex Cloud GPT provider"""
    
    def __init__(self):
        super().__init__("yandex")
        self.api_url = CONFIG.get("yandex_api_url", "https://api.cloud.yandex.net")
        self.api_key = CONFIG.get("yandex_api_key", "")
        self.folder_id = CONFIG.get("yandex_folder_id", "")
        self.models = {
            "yandexgpt": {
                "id": "yandexgpt",
                "name": "Yandex GPT",
                "provider": "yandex",
                "description": "Yandex's large language model",
                "max_tokens": 8192,
                "pricing": {"prompt": 0.005, "completion": 0.015},
                "supported": True,
                "default": True
            },
            "yandexgpt-lite": {
                "id": "yandexgpt-lite",
                "name": "Yandex GPT Lite",
                "provider": "yandex",
                "description": "Faster and cheaper Yandex model",
                "max_tokens": 4096,
                "pricing": {"prompt": 0.002, "completion": 0.005},
                "supported": True,
                "default": False
            }
        }
    
    def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> dict:
        """Generate text using Yandex API"""
        model = kwargs.get("model", "yandexgpt")
        max_tokens = kwargs.get("max_tokens", CONFIG["max_tokens"])
        temperature = kwargs.get("temperature", CONFIG["temperature"])
        
        logger.info(f"Yandex: Generate with {model}, max_tokens={max_tokens}, temperature={temperature}")
        
        # Simulate response
        prompt_tokens = len(prompt.split())
        completion_tokens = 30
        
        # Update stats
        with threading.Lock():
            usage_stats["total_tokens"] += prompt_tokens + completion_tokens
            usage_stats["prompt_tokens"] += prompt_tokens
            usage_stats["completion_tokens"] += completion_tokens
            usage_stats["total_requests"] += 1
            if model not in usage_stats["by_model"]:
                usage_stats["by_model"][model] = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
            usage_stats["by_model"][model]["prompt_tokens"] += prompt_tokens
            usage_stats["by_model"][model]["completion_tokens"] += completion_tokens
            usage_stats["by_model"][model]["requests"] += 1
        
        mock_response = f"Ответ от Yandex GPT: {prompt[:100]}..."
        
        return {
            "status": "success",
            "text": mock_response,
            "model": model,
            "provider": "yandex",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            },
            "latency": 0.8,
            "finish_reason": "stop"
        }


class LocalProvider(LLMProvider):
    """Local LLM provider (Ollama, etc.)"""
    
    def __init__(self):
        super().__init__("local")
        self.api_url = CONFIG.get("local_api_url", "http://localhost:11434")
        self.models = {
            "llama2": {
                "id": "llama2",
                "name": "Llama 2",
                "provider": "local",
                "description": "Meta's Llama 2 model",
                "max_tokens": 4096,
                "pricing": {"prompt": 0.0, "completion": 0.0},
                "supported": True,
                "default": True
            },
            "mistral": {
                "id": "mistral",
                "name": "Mistral",
                "provider": "local",
                "description": "Mistral AI model",
                "max_tokens": 8192,
                "pricing": {"prompt": 0.0, "completion": 0.0},
                "supported": True,
                "default": False
            },
            "phi2": {
                "id": "phi2",
                "name": "Phi-2",
                "provider": "local",
                "description": "Microsoft's Phi-2 model",
                "max_tokens": 4096,
                "pricing": {"prompt": 0.0, "completion": 0.0},
                "supported": True,
                "default": False
            }
        }
    
    def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> dict:
        """Generate text using local LLM"""
        model = kwargs.get("model", "llama2")
        max_tokens = kwargs.get("max_tokens", CONFIG["max_tokens"])
        temperature = kwargs.get("temperature", CONFIG["temperature"])
        
        logger.info(f"Local: Generate with {model}, max_tokens={max_tokens}, temperature={temperature}")
        
        # Simulate response
        prompt_tokens = len(prompt.split())
        completion_tokens = 40
        
        # Update stats
        with threading.Lock():
            usage_stats["total_tokens"] += prompt_tokens + completion_tokens
            usage_stats["prompt_tokens"] += prompt_tokens
            usage_stats["completion_tokens"] += completion_tokens
            usage_stats["total_requests"] += 1
            if model not in usage_stats["by_model"]:
                usage_stats["by_model"][model] = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
            usage_stats["by_model"][model]["prompt_tokens"] += prompt_tokens
            usage_stats["by_model"][model]["completion_tokens"] += completion_tokens
            usage_stats["by_model"][model]["requests"] += 1
        
        mock_response = f"Local LLM response from {model}: Based on your input, I can help you with..."
        
        return {
            "status": "success",
            "text": mock_response,
            "model": model,
            "provider": "local",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            },
            "latency": 2.0,
            "finish_reason": "stop"
        }


# Global providers
providers: Dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "yandex": YandexProvider(),
    "local": LocalProvider()
}


# Conversation manager
class ConversationManager:
    """Manage conversations with LLM"""
    
    def __init__(self):
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    def create_conversation(self, user_id: str, model: str = None, 
                           provider: str = None, system_prompt: str = None,
                           context: dict = None) -> str:
        """Create a new conversation"""
        conversation_id = str(uuid.uuid4())
        
        with self.lock:
            self.conversations[conversation_id] = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "model": model or CONFIG["default_model"],
                "provider": provider or CONFIG["default_provider"],
                "system_prompt": system_prompt,
                "messages": [],
                "context": context or {},
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        
        logger.info(f"Conversation created: {conversation_id} for user {user_id}")
        return conversation_id
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation by ID"""
        with self.lock:
            return self.conversations.get(conversation_id)
    
    def add_message(self, conversation_id: str, role: str, content: str) -> str:
        """Add message to conversation"""
        with self.lock:
            conversation = self.conversations.get(conversation_id)
            if conversation:
                message_id = str(uuid.uuid4())
                conversation["messages"].append({
                    "message_id": message_id,
                    "role": role,
                    "content": content,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                conversation["updated_at"] = datetime.utcnow().isoformat() + "Z"
                
                # If storing is disabled and we have too many messages, trim
                if not CONFIG["store_conversations"] and len(conversation["messages"]) > 100:
                    conversation["messages"] = conversation["messages"][-50:]
                
                return message_id
        return ""
    
    def get_history(self, conversation_id: str, limit: int = 50, offset: int = 0) -> dict:
        """Get conversation history"""
        conversation = self.get_conversation(conversation_id)
        if conversation:
            messages = conversation["messages"]
            total = len(messages)
            paginated = messages[offset:offset + limit]
            
            return {
                "status": "success",
                "messages": paginated,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        return {"status": "error", "error": "Conversation not found"}
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete conversation"""
        with self.lock:
            if conversation_id in self.conversations:
                del self.conversations[conversation_id]
                logger.info(f"Conversation deleted: {conversation_id}")
                return True
            return False
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear conversation messages"""
        with self.lock:
            if conversation_id in self.conversations:
                self.conversations[conversation_id]["messages"] = []
                self.conversations[conversation_id]["updated_at"] = datetime.utcnow().isoformat() + "Z"
                logger.info(f"Conversation cleared: {conversation_id}")
                return True
            return False


# Prompt manager
class PromptManager:
    """Manage prompts and templates"""
    
    def __init__(self):
        self.prompts: Dict[str, Dict[str, Any]] = {
            "default": {
                "prompt_id": "default",
                "name": "Default",
                "template": "You are a helpful AI assistant. Answer the user's question based on the context.",
                "description": "Default conversation prompt",
                "variables": [],
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            },
            "chatbot": {
                "prompt_id": "chatbot",
                "name": "Chatbot",
                "template": "You are a chatbot assistant. Be friendly and helpful. Current date: {current_date}. User: {username}",
                "description": "Chatbot conversation prompt",
                "variables": ["current_date", "username"],
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            },
            "analyst": {
                "prompt_id": "analyst",
                "name": "Data Analyst",
                "template": "You are a data analyst. Analyze the provided data and answer the user's question. Data: {data}",
                "description": "Data analysis prompt",
                "variables": ["data"],
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        }
        self.lock = threading.Lock()
    
    def create_prompt(self, name: str, template: str, description: str = "", 
                     variables: list = None) -> str:
        """Create a new prompt"""
        prompt_id = str(uuid.uuid4())
        
        with self.lock:
            self.prompts[prompt_id] = {
                "prompt_id": prompt_id,
                "name": name,
                "template": template,
                "description": description,
                "variables": variables or [],
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        
        logger.info(f"Prompt created: {prompt_id} - {name}")
        return prompt_id
    
    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get prompt by ID"""
        with self.lock:
            return self.prompts.get(prompt_id)
    
    def update_prompt(self, prompt_id: str, name: str = None, template: str = None,
                     description: str = None, variables: list = None) -> bool:
        """Update prompt"""
        with self.lock:
            if prompt_id in self.prompts:
                prompt = self.prompts[prompt_id]
                if name:
                    prompt["name"] = name
                if template:
                    prompt["template"] = template
                if description:
                    prompt["description"] = description
                if variables:
                    prompt["variables"] = variables
                prompt["updated_at"] = datetime.utcnow().isoformat() + "Z"
                return True
        return False
    
    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete prompt"""
        with self.lock:
            if prompt_id in self.prompts and prompt_id != "default":
                del self.prompts[prompt_id]
                logger.info(f"Prompt deleted: {prompt_id}")
                return True
        return False
    
    def render_prompt(self, prompt_id: str, variables: dict = None) -> dict:
        """Render prompt with variables"""
        prompt = self.get_prompt(prompt_id)
        if prompt:
            template = prompt["template"]
            variables = variables or {}
            
            try:
                rendered = template.format(**variables)
                return {
                    "status": "success",
                    "prompt": rendered,
                    "variables": variables
                }
            except KeyError as e:
                return {
                    "status": "error",
                    "error": f"Missing variable: {e}",
                    "prompt": template
                }
        return {"status": "error", "error": "Prompt not found"}
    
    def list_prompts(self) -> list:
        """List all prompts"""
        with self.lock:
            return list(self.prompts.values())


# Global instances
conversation_manager = ConversationManager()
prompt_manager = PromptManager()


class HTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for LLM module API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        try:
            # List models
            if path == "/api/v1/models":
                all_models = []
                for provider in providers.values():
                    if provider.enabled:
                        for model in provider.list_models():
                            all_models.append(model)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "models": all_models,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get model info
            elif path.startswith("/api/v1/models/"):
                parts = path.split("/")
                model_id = parts[3]
                
                if len(parts) == 4:
                    # Find model
                    model_info = None
                    for provider in providers.values():
                        for model in provider.list_models():
                            if model["id"] == model_id:
                                model_info = model
                                break
                    
                    if model_info:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(model_info, indent=2).encode())
                    else:
                        self.send_error(404, f"Model {model_id} not found")
            
            # List prompts
            elif path == "/api/v1/prompts":
                prompts = prompt_manager.list_prompts()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "prompts": prompts,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get prompt
            elif path.startswith("/api/v1/prompts/"):
                parts = path.split("/")
                prompt_id = parts[3]
                
                if len(parts) == 4:
                    prompt = prompt_manager.get_prompt(prompt_id)
                    if prompt:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(prompt, indent=2).encode())
                    else:
                        self.send_error(404, f"Prompt {prompt_id} not found")
            
            # Get conversation
            elif path.startswith("/api/v1/conversations/"):
                parts = path.split("/")
                conversation_id = parts[3]
                
                if len(parts) == 4:
                    conversation = conversation_manager.get_conversation(conversation_id)
                    if conversation:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(conversation, indent=2).encode())
                    else:
                        self.send_error(404, f"Conversation {conversation_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "history":
                    limit = int(params.get("limit", ["50"])[0])
                    offset = int(params.get("offset", ["0"])[0])
                    history = conversation_manager.get_history(conversation_id, limit, offset)
                    
                    self.send_response(200 if history["status"] == "success" else 404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(history).encode())
            
            # Health check
            elif path == "/api/v1/health":
                provider_statuses = []
                active_models = 0
                for provider_name, provider in providers.items():
                    model_count = len(provider.list_models())
                    active_models += model_count
                    provider_statuses.append({
                        "provider": provider_name,
                        "status": "active" if provider.enabled else "inactive",
                        "models": [m["id"] for m in provider.list_models()],
                        "api_health": "healthy"
                    })
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "healthy",
                    "providers": provider_statuses,
                    "active_models": active_models,
                    "rate_limit_status": {"remaining": CONFIG["max_requests_per_minute"]},
                    "error_rate": 0.0,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get configuration
            elif path == "/api/v1/config":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "default_provider": CONFIG["default_provider"],
                    "default_model": CONFIG["default_model"],
                    "max_tokens": CONFIG["max_tokens"],
                    "temperature": CONFIG["temperature"],
                    "rate_limits": {
                        "max_requests_per_minute": CONFIG["max_requests_per_minute"],
                        "max_tokens_per_minute": CONFIG["max_tokens_per_minute"],
                        "burst_limit": CONFIG["burst_limit"]
                    },
                    "privacy_settings": {
                        "sanitize_input": CONFIG["sanitize_input"],
                        "sanitize_output": CONFIG["sanitize_output"],
                        "content_filter_enabled": CONFIG["content_filter_enabled"],
                        "anonymize_user_data": CONFIG["anonymize_user_data"],
                        "store_conversations": CONFIG["store_conversations"],
                        "log_prompts": CONFIG["log_prompts"]
                    }
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Get usage statistics
            elif path == "/api/v1/stats/usage":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(usage_stats, indent=2).encode())
            
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
            
            # Generate text
            if path == "/api/v1/generate":
                prompt = data.get("prompt", "")
                system_prompt = data.get("system_prompt", "")
                model = data.get("model", CONFIG["default_model"])
                provider = data.get("provider", CONFIG["default_provider"])
                max_tokens = data.get("max_tokens", CONFIG["max_tokens"])
                temperature = data.get("temperature", CONFIG["temperature"])
                
                # Get provider
                llm_provider = providers.get(provider)
                if llm_provider:
                    result = llm_provider.generate(
                        prompt,
                        system_prompt,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    
                    if CONFIG["sanitize_output"] and result.get("status") == "success":
                        result["text"] = sanitize_text(result["text"])
                    
                    self.send_response(200 if result["status"] == "success" else 400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result, indent=2).encode())
                else:
                    self.send_error(400, f"Provider {provider} not found")
            
            # Chat completion
            elif path == "/api/v1/chat":
                messages = data.get("messages", [])
                model = data.get("model", CONFIG["default_model"])
                provider = data.get("provider", CONFIG["default_provider"])
                max_tokens = data.get("max_tokens", CONFIG["max_tokens"])
                temperature = data.get("temperature", CONFIG["temperature"])
                
                llm_provider = providers.get(provider)
                if llm_provider:
                    result = llm_provider.chat(
                        messages,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    
                    if CONFIG["sanitize_output"] and result.get("status") == "success":
                        if "message" in result:
                            result["message"]["content"] = sanitize_text(result["message"]["content"])
                    
                    self.send_response(200 if result["status"] == "success" else 400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result, indent=2).encode())
                else:
                    self.send_error(400, f"Provider {provider} not found")
            
            # Analyze intent
            elif path == "/api/v1/analyze/intent":
                text = data.get("text", "")
                context = data.get("context", "")
                model = data.get("model", CONFIG["default_model"])
                
                # Use default provider
                llm_provider = providers.get(CONFIG["default_provider"])
                if llm_provider:
                    # Mock intent analysis
                    prompt = f"Analyze the intent of this text: {text}\n\nContext: {context}\n\nIntent categories: greeting, question, request, command, information, complaint.\nReturn only the most likely intent and confidence score."
                    
                    result = llm_provider.generate(prompt, model=model)
                    
                    if result.get("status") == "success":
                        # Parse mock response
                        text = result["text"]
                        intent = "question"
                        confidence = 0.9
                        
                        if "greeting" in text.lower():
                            intent = "greeting"
                            confidence = 0.95
                        elif "command" in text.lower():
                            intent = "command"
                            confidence = 0.85
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "intent": intent,
                            "confidence": confidence,
                            "entities": [],
                            "classification": {"intent": intent, "confidence": confidence}
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                    else:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode())
            
            # Moderate content
            elif path == "/api/v1/moderate":
                text = data.get("text", "")
                
                is_safe, moderation = moderate_content(text)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(moderation, indent=2).encode())
            
            # Create conversation
            elif path == "/api/v1/conversations":
                user_id = data.get("user_id", str(uuid.uuid4()))
                model = data.get("model", CONFIG["default_model"])
                provider = data.get("provider", CONFIG["default_provider"])
                system_prompt = data.get("system_prompt", "")
                context = data.get("context", {})
                
                conversation_id = conversation_manager.create_conversation(
                    user_id, model, provider, system_prompt, context
                )
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "conversation_id": conversation_id,
                    "message": "Conversation created"
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
            
            # Add message to conversation
            elif path.startswith("/api/v1/conversations/"):
                parts = path.split("/")
                conversation_id = parts[3]
                
                if len(parts) >= 5 and parts[4] == "messages":
                    role = data.get("role", "user")
                    content = data.get("content", "")
                    
                    message_id = conversation_manager.add_message(
                        conversation_id, role, content
                    )
                    
                    if message_id:
                        self.send_response(201)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message_id": message_id,
                            "message": {
                                "role": role,
                                "content": content,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }
                        }
                        self.wfile.write(json.dumps(response, indent=2).encode())
                    else:
                        self.send_error(404, f"Conversation {conversation_id} not found")
                
                elif len(parts) >= 5 and parts[4] == "clear":
                    if conversation_manager.clear_conversation(conversation_id):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": "Conversation cleared"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, f"Conversation {conversation_id} not found")
            
            # Create prompt
            elif path == "/api/v1/prompts":
                name = data.get("name", "")
                template = data.get("template", "")
                description = data.get("description", "")
                variables = data.get("variables", [])
                
                prompt_id = prompt_manager.create_prompt(
                    name, template, description, variables
                )
                
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "prompt_id": prompt_id,
                    "message": "Prompt created"
                }
                self.wfile.write(json.dumps(response).encode())
            
            # Render prompt
            elif path.startswith("/api/v1/prompts/"):
                parts = path.split("/")
                prompt_id = parts[3]
                
                if len(parts) >= 5 and parts[4] == "render":
                    variables = data.get("variables", {})
                    result = prompt_manager.render_prompt(prompt_id, variables)
                    
                    self.send_response(200 if result["status"] == "success" else 400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result, indent=2).encode())
            
            # Update configuration
            elif path == "/api/v1/config":
                for key, value in data.items():
                    if key in CONFIG:
                        CONFIG[key] = value
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "message": "Configuration updated"
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
            
            # Update prompt
            if path.startswith("/api/v1/prompts/"):
                parts = path.split("/")
                prompt_id = parts[3]
                
                if len(parts) == 4:
                    name = data.get("name")
                    template = data.get("template")
                    description = data.get("description")
                    variables = data.get("variables")
                    
                    if prompt_manager.update_prompt(
                        prompt_id, name, template, description, variables
                    ):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": "Prompt updated"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, f"Prompt {prompt_id} not found")
            
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
            # Delete prompt
            if path.startswith("/api/v1/prompts/"):
                parts = path.split("/")
                prompt_id = parts[3]
                
                if len(parts) == 4:
                    if prompt_manager.delete_prompt(prompt_id):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": f"Prompt {prompt_id} deleted"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, f"Prompt {prompt_id} not found")
            
            # Delete conversation
            elif path.startswith("/api/v1/conversations/"):
                parts = path.split("/")
                conversation_id = parts[3]
                
                if len(parts) == 4:
                    if conversation_manager.delete_conversation(conversation_id):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "status": "success",
                            "message": f"Conversation {conversation_id} deleted"
                        }
                        self.wfile.write(json.dumps(response).encode())
                    else:
                        self.send_error(404, f"Conversation {conversation_id} not found")
            
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
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="UniBot LLM Module")
    parser.add_argument("--port", type=int, default=CONFIG["listen_port"], help="Port to listen on")
    parser.add_argument("--host", type=str, default=CONFIG["listen_address"], help="Host to listen on")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Update config from args
    CONFIG["listen_port"] = args.port
    CONFIG["listen_address"] = args.host
    
    # Load configuration
    load_config()
    
    logger.info(f"Starting UniBot LLM Module v{MODULE_VERSION}")
    logger.info(f"Listening on {CONFIG['listen_address']}:{CONFIG['listen_port']}")
    logger.info(f"Default provider: {CONFIG['default_provider']}, Default model: {CONFIG['default_model']}")
    
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
        logger.info("LLM module stopped")


if __name__ == "__main__":
    main()
