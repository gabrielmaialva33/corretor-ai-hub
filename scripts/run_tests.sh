#!/bin/bash

# Script to run tests for Corretor AI Hub

echo "=== Corretor AI Hub - Test Runner ==="
echo ""

# Change to project directory
cd "$(dirname "$0")/.." || exit 1

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1

# Load test environment
export ENVIRONMENT=test
export TESTING=true

# Check if test database exists
echo "Checking test database..."
if ! PGPASSWORD=postgres psql -h localhost -U postgres -lqt | cut -d \| -f 1 | grep -qw corretor_test; then
    echo "Test database not found. Creating..."
    ./scripts/setup_test_db.sh
fi

# Run tests
echo ""
echo "Running tests..."
echo "=================="

# Run specific test categories
if [ "$1" == "unit" ]; then
    echo "Running unit tests only..."
    python -m pytest tests/ -v -m unit
elif [ "$1" == "integration" ]; then
    echo "Running integration tests only..."
    python -m pytest tests/ -v -m integration
elif [ "$1" == "coverage" ]; then
    echo "Running tests with coverage..."
    python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
elif [ "$1" == "fast" ]; then
    echo "Running fast tests only..."
    python -m pytest tests/ -v -m "not slow"
else
    echo "Running all tests..."
    python -m pytest tests/ -v
fi

# Deactivate virtual environment
deactivate

echo ""
echo "Test run complete!"