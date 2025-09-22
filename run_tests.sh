#!/bin/bash

# Run tests script
echo "Running TurnosLibres test suite..."

# Set test environment
export FLASK_ENV=testing
export TESTING=1

# Install test dependencies if needed
pip install pytest pytest-cov

# Run tests with coverage
pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

# Check test results
if [ $? -eq 0 ]; then
    echo "✅ All tests passed!"
    echo "📊 Coverage report generated in htmlcov/"
else
    echo "❌ Some tests failed!"
    exit 1
fi
