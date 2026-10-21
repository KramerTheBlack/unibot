#!/bin/bash
# UniBot Docker Image Push Script
# Version: 2026.10.21_1
# This script pushes all Docker images to Docker Hub

set -e

echo "=========================================="
echo "UniBot Docker Image Push Script"
echo "Version: 2026.10.21_1"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running!${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi

# Check if user is logged in to Docker Hub
if ! docker login status > /dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Not logged in to Docker Hub${NC}"
    echo "Please run 'docker login' and try again."
    read -p "Do you want to continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}Docker daemon is running.${NC}"
echo ""

# Modules to push
MODULES=("core" "auth" "web" "datastore" "multichat" "llm" "menu" "apps")
VERSION="2026.10.21_1"
DOCKER_REPO="kramertheblack/unibot"

# Function to push a module
push_module() {
    local module="$1"
    echo -e "${YELLOW}Pushing ${module} module...${NC}"
    
    docker push "${DOCKER_REPO}:${module}-${VERSION}" 2>&1 | tail -5
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully pushed ${DOCKER_REPO}:${module}-${VERSION}${NC}"
    else
        echo -e "${RED}Error: Failed to push ${module} module${NC}"
        exit 1
    fi
    
    echo ""
}

# Push all modules
for module in "${MODULES[@]}"; do
    push_module "$module"
done

echo "=========================================="
echo -e "${GREEN}All modules pushed successfully!${NC}"
echo "=========================================="
echo ""
echo "Images are now available on Docker Hub at:"
echo "  https://hub.docker.com/r/${DOCKER_REPO}"
echo ""
echo "To deploy with docker-compose, run:"
echo "  docker-compose pull && docker-compose up -d"
