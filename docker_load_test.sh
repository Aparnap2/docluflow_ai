#!/bin/bash
# Docker-based load test with resource monitoring

set -e

echo "=========================================="
echo "PropFlow Agent Docker Load Test"
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Use uv Python image for faster package installation
IMAGE="astral/uv:python3.11-trixie-slim"
CONTAINER_NAME="propflow-loadtest-$(date +%s)"

echo "📦 Using image: $IMAGE (includes uv for fast package installation)"
echo "📝 Container name: $CONTAINER_NAME"
echo ""

# Build and run container with generous resource limits
# Note: Docling uses PyTorch (memory intensive) and Ollama runs on CPU (slow)
echo "🔨 Building and running container..."
echo "   Memory limit: 2GB (PyTorch/Docling needs more)"
echo "   CPU limit: 2.0 cores (CPU-only Ollama needs more)"
echo ""

# Start container in background and capture PID
docker run -d \
    --name "$CONTAINER_NAME" \
    --memory="2g" \
    --cpus="2.0" \
    -v "$(pwd):/app" \
    -w /app \
    "$IMAGE" \
    bash -c "
        set -e && \
        uv venv /venv && \
        export VIRTUAL_ENV=/venv && \
        export PATH=\"/venv/bin:\$PATH\" && \
        echo 'Installing dependencies (this may take a while with PyTorch)...' && \
        uv pip install -r requirements.txt && \
        echo 'Starting load test...' && \
        /venv/bin/python load_test.py
    " > /dev/null

echo "⏳ Container started. Monitoring resources..."
echo ""

# Wait longer for container to initialize (PyTorch/Docling setup takes time)
echo "⏳ Waiting for container initialization (PyTorch/Docling setup)..."
sleep 10

# Monitor container resources
echo "📊 Real-time Resource Monitoring (updating every 5 seconds):"
echo "=========================================="
printf "%-20s %-10s %-15s %-10s %-15s\n" "TIME" "CPU%" "MEMORY" "MEM%" "STATUS"
echo "------------------------------------------------------------"

COUNTER=0
MAX_ITERATIONS=180  # Monitor for up to 15 minutes (generous timeout)

while [ $COUNTER -lt $MAX_ITERATIONS ]; do
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "Container finished."
        break
    fi
    
    STATS=$(docker stats --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" "$CONTAINER_NAME" 2>/dev/null)
    if [ ! -z "$STATS" ]; then
        CPU=$(echo "$STATS" | cut -f1)
        MEM=$(echo "$STATS" | cut -f2)
        MEM_PERC=$(echo "$STATS" | cut -f3)
        TIME=$(date +%H:%M:%S)
        printf "%-20s %-10s %-15s %-10s %-15s\n" "$TIME" "$CPU" "$MEM" "$MEM_PERC" "Running"
    fi
    
    sleep 5  # Check every 5 seconds (less frequent updates)
    COUNTER=$((COUNTER + 1))
done

echo ""
echo "=========================================="
echo "📋 Container Output:"
echo "=========================================="
docker logs "$CONTAINER_NAME" 2>&1 | tail -80

echo ""
echo "=========================================="
echo "📊 Final Resource Statistics:"
echo "=========================================="
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}" "$CONTAINER_NAME" 2>/dev/null || echo "Container has finished"

# Get peak memory usage from Docker stats history
echo ""
echo "=========================================="
echo "🔍 Resource Analysis:"
echo "=========================================="

# Check if container is still running
if docker ps -a | grep -q "$CONTAINER_NAME"; then
    CONTAINER_INFO=$(docker inspect "$CONTAINER_NAME" --format='{{.State.Status}}')
    echo "Container Status: $CONTAINER_INFO"
    
    # Get memory stats
    MEM_STATS=$(docker stats --no-stream --format "{{.MemUsage}}" "$CONTAINER_NAME" 2>/dev/null || echo "0B / 0B")
    echo "Memory Usage: $MEM_STATS"
    
    # Get exit code
    EXIT_CODE=$(docker inspect "$CONTAINER_NAME" --format='{{.State.ExitCode}}')
    echo "Exit Code: $EXIT_CODE"
fi

echo ""
echo "🧹 Cleaning up..."
docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true

echo ""
echo "✅ Load test complete!"
echo ""
echo "💡 Resource Usage Analysis:"
echo "   - PyTorch (Docling): Typically uses 200-500MB base memory"
echo "   - Ollama (CPU-only): Slower but uses less GPU memory"
echo "   - Peak memory during processing: Monitor for memory leaks"
echo ""
echo "💡 Optimization Tips:"
echo "   - Memory > 1.5GB: Consider reducing batch sizes or using GPU"
echo "   - CPU consistently > 80%: Consider horizontal scaling or GPU acceleration"
echo "   - Slow processing: Expected with CPU-only Ollama; consider GPU for production"
echo "   - Docling: Can be optimized by disabling unused features"
echo "   - Consider caching OCR results for repeated documents"
