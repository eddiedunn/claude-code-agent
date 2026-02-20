"""Prometheus metrics for grind-server."""
from prometheus_client import Counter, Histogram, Gauge, Info

# Server info
grind_server_info = Info('grind_server', 'Grind server information')
grind_server_info.info({'version': '0.1.0'})

# Session metrics
sessions_total = Counter(
    'grind_sessions_total',
    'Total number of sessions',
    ['status']  # completed, failed, cancelled
)

sessions_active = Gauge(
    'grind_sessions_active',
    'Currently active sessions'
)

session_duration_seconds = Histogram(
    'grind_session_duration_seconds',
    'Session duration in seconds',
    buckets=[30, 60, 120, 300, 600, 1800, 3600]  # 30s to 1h
)

# Task metrics
tasks_total = Counter(
    'grind_tasks_total',
    'Total number of tasks executed',
    ['status', 'model']  # status: completed/failed, model: sonnet/opus/haiku
)

task_duration_seconds = Histogram(
    'grind_task_duration_seconds',
    'Task duration in seconds',
    ['model'],
    buckets=[10, 30, 60, 120, 300, 600, 1200]  # 10s to 20m
)

# Iteration metrics
iterations_total = Counter(
    'grind_iterations_total',
    'Total number of iterations across all sessions'
)

retries_total = Counter(
    'grind_retries_total',
    'Total number of task retries'
)

# Error metrics
errors_total = Counter(
    'grind_errors_total',
    'Total errors by type',
    ['error_type']  # timeout, api_error, validation_error, etc.
)
