#!/bin/bash

# Neural Agent System - Quick Start Script

set -e

echo "========================================="
echo "Neural Agent System - Starting..."
echo "========================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not installed"
    exit 1
fi

# Check if .env file exists
if [ ! -f backend/.env ]; then
    echo "Creating .env file from template..."
    cp backend/.env.example backend/.env
    echo "Please edit backend/.env and add your API keys"
    echo "Then run this script again"
    exit 0
fi

# Pull latest images (optional)
echo "Pulling latest images..."
docker compose pull 2>/dev/null || true

# Start all services
echo "Starting all services..."
docker compose up -d

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 10

# Check service status
echo ""
echo "========================================="
echo "Service Status:"
echo "========================================="
docker compose ps

echo ""
echo "========================================="
echo "Access Points:"
echo "========================================="
echo "- API Server:      http://localhost:8000"
echo "- API Docs:        http://localhost:8000/docs"
echo "- RabbitMQ:        http://localhost:15672 (guest/guest)"
echo "- Prometheus:      http://localhost:9090"
echo "- Grafana:         http://localhost:3000 (admin/admin)"
echo "- Milvus:          http://localhost:9091"
echo "- Ray Dashboard:   http://localhost:8265"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop:      docker compose down"
echo "========================================="