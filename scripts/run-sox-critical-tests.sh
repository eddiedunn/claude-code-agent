#!/bin/bash
# Run SOX-critical tests that MUST pass for production deployment

set -e

echo "Running SOX-critical compliance tests..."
echo "These tests MUST achieve 100% pass rate for production."
echo ""

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    echo "WARNING: Docker is not available. Skipping MinIO startup."
    echo "Running tests directly (may fail if external services are required)."
    echo ""
else
    # Check if docker-compose.ci.yml exists
    if [ -f "docker-compose.ci.yml" ]; then
        echo "Starting MinIO for testing..."
        docker compose -f docker-compose.ci.yml up -d minio || true
        sleep 5
    else
        echo "INFO: docker-compose.ci.yml not found, skipping MinIO startup"
    fi
fi

echo "Running pytest with sox_critical marker..."
python -m pytest \
  -m "sox_critical" \
  -v \
  --tb=short \
  --strict-markers \
  -x

EXIT_CODE=$?

# Cleanup if docker compose was used
if command -v docker &> /dev/null && [ -f "docker-compose.ci.yml" ]; then
    echo ""
    echo "Cleaning up Docker resources..."
    docker compose -f docker-compose.ci.yml down -v || true
fi

if [ $EXIT_CODE -eq 0 ]; then
  echo ""
  echo "✓ All SOX-critical tests passed"
  exit 0
else
  echo ""
  echo "✗ SOX-critical tests failed - deployment blocked"
  exit 1
fi
