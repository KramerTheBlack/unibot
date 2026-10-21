# UniBot

**Modular Chat-Bot Constructor for Messengers**

Version: 2026.10.21_1

UniBot is a modular, extensible platform for creating chat-bots that work across multiple messaging platforms (VK, Telegram, MAX Messenger). The system is designed with a microservices architecture where each module operates as an independent service that can be developed, deployed, and scaled separately.

## Features

- **Modular Architecture**: Each component (authentication, database, AI, etc.) is a separate module
- **Multi-Platform**: Support for VK, Telegram, MAX Messenger
- **AI Integration**: Connect with OpenAI, Yandex, or local LLM providers
- **Dynamic Menus**: Flexible menu system for bot navigation
- **Web Console**: Administration interface for managing the bot
- **Extensible**: Add custom functional modules via the apps system

## Architecture

### Core Modules

1. **core** - Central module that manages communication between all modules
   - Message queue for async communication
   - Module registry and health monitoring
   - Centralized logging
   - Cache management

2. **auth** - Authentication and authorization
   - User management (administrators, customers, anonymous)
   - Session management
   - Role-based access control
   - Default admin: `unibotadmin` / `tellmepass`

3. **web** - Web administration console
   - User and group management
   - Module configuration
   - Menu management
   - LLM configuration
   - Default port: 8080

4. **datastore** - Database and storage management
   - SQLite, PostgreSQL, MySQL, MSSQL support
   - Connection pooling
   - Query execution
   - Default port: 5002

5. **multichat** - Chat platform integration
   - VK, Telegram, MAX Messenger support
   - Webhook processing
   - Command routing
   - Default port: 5003

6. **llm** - AI/ML integration
   - OpenAI, Yandex, Local provider support
   - Text generation
   - Chat completion
   - Moderation
   - Default port: 5004

7. **menu** - Navigation and menu management
   - Hierarchical menu structure
   - Command routing
   - Access control
   - Default port: 5005

8. **apps** - Dynamic functional module loader
   - Loads submodules from `modules/apps/` directory
   - Current submodules: store, queue, test, tracking
   - Default port: 5006

### Module Files

Each module contains:
- `module.yml` - Module metadata (name, version, description, dependencies)
- `module.conf` - Configuration parameters
- `module.api` - API specification (endpoints, commands, events)
- `about.txt` - Human-readable description of the module
- `*.py` - Implementation file(s)
- `Dockerfile` - Docker container definition

## Quick Start

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- Git
- Minimum 4GB RAM, 2 CPU cores

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/KramerTheBlack/unibot.git
cd unibot

# Create secrets directory (if not exists)
mkdir -p secrets

# Copy example secrets
cp secrets.example/* secrets/ 2>/dev/null || true
```

### 2. Configure Secrets

Edit the following files in the `secrets/` directory:

- `auth.conf` - Authentication module secrets (default admin credentials)
- `vk.bots.secret` - VK bot tokens
- `max.bots.secret` - MAX Messenger bot tokens
- `tg.bots.secret` - Telegram bot tokens
- `llm.secret` - LLM API keys (OpenAI, Yandex, etc.)
- `app.*.secret` - Functional module secrets

### 3. Build Docker Images

#### Option A: Using Docker Compose (Recommended)

```bash
# Build all images
docker-compose build

# Or build specific modules
docker-compose build core auth web
```

#### Option B: Manual Build

**On Linux/macOS:**
```bash
# Make scripts executable
chmod +x build-images.sh push-images.sh

# Build all images
./build-images.sh

# Or build specific module
cd modules/core
docker build -t kramertheblack/unibot:core-2026.10.21_1 .
```

**On Windows:**
```batch
:: Build all images
build-images.bat

:: Or build specific module
cd modules\core
docker build -t kramertheblack/unibot:core-2026.10.21_1 .
```

### 4. Push to Docker Hub

Before pushing, ensure you're logged in:

```bash
docker login
```

Then push all images:

**Linux/macOS:**
```bash
./push-images.sh
```

**Windows:**
```batch
push-images.bat
```

Or push manually:
```bash
docker push kramertheblack/unibot:core-2026.10.21_1
docker push kramertheblack/unibot:auth-2026.10.21_1
docker push kramertheblack/unibot:web-2026.10.21_1
docker push kramertheblack/unibot:datastore-2026.10.21_1
docker push kramertheblack/unibot:multichat-2026.10.21_1
docker push kramertheblack/unibot:llm-2026.10.21_1
docker push kramertheblack/unibot:menu-2026.10.21_1
docker push kramertheblack/unibot:apps-2026.10.21_1
```

### 5. Deploy with Docker Compose

```bash
# Pull images from Docker Hub (if not built locally)
docker-compose pull

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### 6. Access the System

- **Web Console**: http://localhost:8080
- **Core API**: http://localhost:5000
- **Auth API**: http://localhost:5001
- **Datastore API**: http://localhost:5002
- **MultiChat API**: http://localhost:5003
- **LLM API**: http://localhost:5004
- **Menu API**: http://localhost:5005
- **Apps API**: http://localhost:5006

## Configuration

### Environment Variables

Each module can be configured via environment variables or configuration files.

**Core Module:**
```bash
CORE_PORT=5000
MODULE_NAME=core
MODULE_VERSION=2026.10.21_1
```

**Auth Module:**
```bash
AUTH_PORT=5001
MODULE_NAME=auth
MODULE_VERSION=2026.10.21_1
```

### Ports

| Module | Port | Description |
|--------|------|-------------|
| core | 5000 | Central module API |
| auth | 5001 | Authentication API |
| datastore | 5002 | Database API |
| multichat | 5003 | Chat integration API |
| llm | 5004 | LLM API |
| menu | 5005 | Menu API |
| apps | 5006 | Apps module API |
| web | 8080 | Web administration console |
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache |

## API Documentation

Each module provides a RESTful HTTP API. See the `module.api` file in each module directory for detailed API specifications.

### Common Endpoints

All modules support:
- `GET /api/v1/health` - Health check
- `GET /api/v1/info` - Module information

### Core Module API

- `GET /api/v1/modules` - List all registered modules
- `GET /api/v1/modules/{name}/status` - Get module status
- `POST /api/v1/modules/register` - Register a new module
- `GET /api/v1/queue/metrics` - Queue metrics
- `GET /api/v1/cache/metrics` - Cache metrics
- `POST /api/v1/queue/send` - Send a message to queue

### Auth Module API

- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/logout` - User logout
- `GET /api/v1/users` - List users (admin only)
- `POST /api/v1/users` - Create user (admin only)
- `GET /api/v1/users/{id}` - Get user info

### Web Module

The web console is accessible at http://localhost:8080 after starting the services.

Default admin credentials:
- Username: `unibotadmin`
- Password: `tellmepass`

## Security

### Secrets Management

All sensitive information (passwords, API keys, tokens) should be stored in the `secrets/` directory and mounted as read-only volumes in Docker.

**Never commit secrets to version control!**

### SSL/TLS

For production deployment, enable SSL/TLS:

1. Generate or obtain SSL certificates
2. Update module configurations to enable SSL
3. Update docker-compose.yml to mount certificate files

## Development

### Module Development

To create a new module:

1. Create a new directory in `modules/`
2. Add `module.yml` with module metadata
3. Add `module.conf` with configuration
4. Add `module.api` with API specification
5. Add `about.txt` with description
6. Implement the module in Python
7. Create a `Dockerfile`
8. Update `docker-compose.yml` to include the module

### Testing

```bash
# Test a specific module
cd modules/core
python core.py --port 5000

# Test with curl
curl http://localhost:5000/api/v1/health

# Run all tests
./run-tests.sh
```

## Troubleshooting

### Docker Desktop Not Running

On Windows/macOS, ensure Docker Desktop is running before executing Docker commands.

### Port Conflicts

If ports are already in use:
```bash
# Find which process is using a port (Linux/macOS)
lsof -i :5000

# On Windows
netstat -ano | findstr :5000
```

### Logs

View module logs:
```bash
# Using docker-compose
docker-compose logs core
docker-compose logs auth

# Direct Docker commands
docker logs unibot-core
docker logs unibot-auth
```

### Database Connection Issues

Ensure PostgreSQL and Redis are running:
```bash
docker-compose ps
docker-compose logs postgres
docker-compose logs redis
```

## Versioning

UniBot uses the following versioning scheme:
```
YEAR.MONTH.DAY_INCREMENTAL_NUMBER
```

For example:
- `2026.10.21_1` - First build on October 21, 2026
- `2026.10.21_2` - Second build on the same day
- `2026.10.22_1` - First build on October 22, 2026

The version is updated each time a successful build is published to GitHub and Docker Hub.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Update documentation
6. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Contact

- GitHub: https://github.com/KramerTheBlack/unibot
- Docker Hub: https://hub.docker.com/r/kramertheblack/unibot

## Directory Structure

```
unibot/
├── README.md                    # Project documentation
├── docker-compose.yml           # Docker Compose configuration
├── .dockerignore                # Docker ignore file
├── init-db.sql                 # Database initialization script
├── build-images.sh              # Build script (Linux/macOS)
├── build-images.bat             # Build script (Windows)
├── push-images.sh               # Push script (Linux/macOS)
├── push-images.bat              # Push script (Windows)
├── modules/                     # All UniBot modules
│   ├── core/                    # Core module
│   │   ├── module.yml           # Module metadata
│   │   ├── module.conf          # Configuration
│   │   ├── module.api           # API specification
│   │   ├── about.txt            # Description
│   │   ├── core.py              # Implementation
│   │   └── Dockerfile           # Docker container
│   ├── auth/                    # Authentication module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── auth.py
│   │   └── Dockerfile
│   ├── web/                     # Web console module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── web.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── datastore/               # Database module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── datastore.py
│   │   └── Dockerfile
│   ├── multichat/               # Chat integration module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── multichat.py
│   │   └── Dockerfile
│   ├── llm/                     # LLM/AI module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── llm.py
│   │   └── Dockerfile
│   ├── menu/                    # Menu module
│   │   ├── module.yml
│   │   ├── module.conf
│   │   ├── module.api
│   │   ├── about.txt
│   │   ├── menu.py
│   │   └── Dockerfile
│   └── apps/                    # Functional modules
│       ├── module.yml
│       ├── module.conf
│       ├── module.api
│       ├── about.txt
│       ├── apps.py
│       ├── Dockerfile
│       ├── app.store/           # Store module
│       ├── app.queue/           # Queue module
│       ├── app.test/            # Test module
│       └── app.tracking/        # Tracking module
├── secrets/                    # Secrets (NOT in version control)
│   ├── auth.conf               # Auth secrets
│   ├── vk.bots.secret          # VK bot tokens
│   ├── max.bots.secret         # MAX bot tokens
│   ├── tg.bots.secret          # Telegram bot tokens
│   ├── llm.secret              # LLM API keys
│   ├── app.store.secret        # Store module secrets
│   ├── app.queue.secret        # Queue module secrets
│   ├── app.test.secret         # Test module secrets
│   └── app.tracking.secret      # Tracking module secrets
├── secrets.example/            # Example secrets (can be committed)
└── vibe/                       # Internal configuration
    ├── instr.txt               # Instructions
    └── pass.txt                # Credentials (NOT in version control)
```

## Status

- [x] Core module implemented
- [x] Auth module implemented
- [x] Web module implemented
- [x] Datastore module implemented
- [x] MultiChat module implemented
- [x] LLM module implemented
- [x] Menu module implemented
- [x] Apps module implemented
- [x] Dockerfiles created for all modules
- [x] docker-compose.yml created
- [x] Secrets configuration created
- [x] Documentation updated
- [ ] Docker images built (requires Docker Desktop)
- [ ] Docker images pushed to Docker Hub (requires Docker Desktop + login)
- [ ] GitHub repository published

## Next Steps

1. **Start Docker Desktop** on your system
2. **Run** `build-images.bat` (Windows) or `./build-images.sh` (Linux/macOS)
3. **Login to Docker Hub** with `docker login`
4. **Push images** with `push-images.bat` or `./push-images.sh`
5. **Test deployment** with `docker-compose up -d`
6. **Verify** all services are running with `docker-compose ps`
7. **Publish to GitHub** after successful testing

## Notes

- All modules are designed to work independently and communicate via HTTP APIs
- The core module acts as a message broker between modules
- Each module has its own HTTP API for direct access
- The web module provides a unified administration interface
- Secrets must be configured before starting the modules
- For production, use proper TLS/SSL configuration
