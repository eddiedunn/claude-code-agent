# Testing Guide

This document describes the testing infrastructure and how to run tests categorized by markers.

## Test Markers

The project uses pytest markers to categorize tests by their purpose and requirements. This allows for selective test execution based on specific needs.

### Available Markers

- **integration**: Integration tests requiring MinIO/external services
- **sox_critical**: SOX-critical tests that MUST pass in production (100% required)
- **security**: Security control tests (authentication, authorization, input validation)
- **worm**: WORM immutability tests (deletion/modification prevention)
- **audit_trail**: Audit logging and trail completeness tests
- **authorization**: Authorization and access control tests
- **concurrency**: Threading and race condition tests
- **production_smoke**: Production configuration validation tests

## Running Tests by Category

### Run only security tests
```bash
pytest -m security
```

### Run only SOX-critical tests (must pass for production)
```bash
pytest -m sox_critical --strict-markers
```

### Run WORM immutability tests
```bash
pytest -m worm
```

### Run audit trail tests
```bash
pytest -m audit_trail
```

### Run concurrency tests
```bash
pytest -m concurrency
```

### Run production smoke tests before deployment
```bash
pytest -m production_smoke
```

### Run all compliance tests (security + worm + audit_trail)
```bash
pytest -m "security or worm or audit_trail"
```

### Run all integration tests
```bash
pytest -m integration
```

## SOX-Critical Test Execution

For production deployments, use the dedicated script to ensure SOX-critical tests pass:

```bash
./scripts/run-sox-critical-tests.sh
```

This script:
1. Starts MinIO service (if available)
2. Runs all tests marked with `@pytest.mark.sox_critical`
3. Exits with code 0 if all tests pass
4. Exits with code 1 if any test fails (blocking deployment)
5. Cleans up Docker resources

## Test Configuration

Pytest configuration is defined in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: Integration tests requiring MinIO/external services",
    "sox_critical: SOX-critical tests that MUST pass in production (100% required)",
    "security: Security control tests (authentication, authorization, input validation)",
    "worm: WORM immutability tests (deletion/modification prevention)",
    "audit_trail: Audit logging and trail completeness tests",
    "authorization: Authorization and access control tests",
    "concurrency: Threading and race condition tests",
    "production_smoke: Production configuration validation tests",
]
```

## Security Testing

### Overview
Security tests verify access controls, rate limiting, DOS prevention, and input validation.
Located in: tests/integration/test_security_controls.py

### Test Categories
- **Access Control**: Authentication, authorization, privilege escalation prevention
- **Rate Limiting**: Per-user rate limits on critical endpoints
- **DOS Prevention**: Large payloads, malformed input, resource exhaustion
- **Input Validation**: SHA validation, path traversal, XSS prevention
- **Security Headers**: HTTP security headers in responses

### Running Security Tests
```bash
# All security tests
pytest -m security -v

# Specific category
pytest tests/integration/test_security_controls.py::TestAccessControl -v

# In Docker
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest tests/integration/test_security_controls.py -v
```

### Note on Rate Limiting
Rate limiter is disabled by default in integration tests (conftest.py).
Rate limiting tests temporarily enable it for validation.
Production rate limits: approve=5/min, check-pr=10/min, status=30/min.

## SOX Compliance Testing

### Overview
WORM (Write Once Read Many) immutability tests prove SOX compliance.
Located in: tests/integration/test_audit_trail.py::TestWORMImmutability

### What is WORM?
WORM storage ensures approval records cannot be deleted or modified after creation.
This is REQUIRED for SOX compliance audit trails.

### S3 Bucket Requirements for Production

**CRITICAL**: Production S3 bucket MUST have these features enabled:

1. **Object Lock**: ENABLED in COMPLIANCE mode (not GOVERNANCE)
   - Prevents deletion of objects until retention expires
   - COMPLIANCE mode: even root users cannot delete
   - Retention period: 7 years minimum (SOX requirement)

2. **Versioning**: ENABLED
   - Preserves all versions of objects
   - Prevents modification (creates new version instead)
   - Original version always retrievable

3. **Encryption**: ENABLED (AES-256 or KMS)
   - Encrypts data at rest
   - Required for sensitive compliance data

4. **Access Logging**: ENABLED to separate audit bucket
   - Logs all access to approval records
   - Separate bucket for audit logs (cannot be in same bucket)

5. **IAM Policies**: Least privilege
   - Only compliance service can write
   - Auditors can read
   - No one can delete

### MinIO vs Production Differences

| Feature | MinIO (Test) | Production S3 |
|---------|--------------|---------------|
| Object Lock | Not supported | REQUIRED |
| Versioning | Supported | REQUIRED |
| Encryption | Supported | REQUIRED |
| Retention | Not enforced | 7 years |
| Tests | Some XFAIL | All MUST pass |

### Running Compliance Tests
```bash
# All WORM tests
pytest tests/integration/test_audit_trail.py::TestWORMImmutability -v

# Only SOX-critical tests (must pass in production)
pytest -m sox_critical -v

# Production smoke tests
pytest -m production_smoke -v
```

### Expected Test Results
- MinIO: 12-15 tests, some XFAIL (Object Lock not supported)
- Production: ALL tests MUST pass (100% required)

### Verifying Production WORM Configuration
```bash
# Check Object Lock
aws s3api get-object-lock-configuration --bucket compliance-approvals

# Check Versioning
aws s3api get-bucket-versioning --bucket compliance-approvals

# Check Encryption
aws s3api get-bucket-encryption --bucket compliance-approvals
```

## Concurrency and Thread Safety Testing

### Overview
Concurrency tests verify race condition handling and thread safety.
Located in: tests/integration/test_concurrent_operations.py::TestActualThreading

### Test Categories
- **Basic Threading**: Multiple threads accessing same/different resources
- **Race Conditions**: Simultaneous approve/reject, double approval
- **Idempotency**: Same operation repeated should not duplicate
- **S3 Consistency**: Read-after-write, list-after-write
- **Resource Exhaustion**: Connection pools, file descriptors

### Running Concurrency Tests
```bash
# All concurrency tests
pytest -m concurrency -v

# Specific test class
pytest tests/integration/test_concurrent_operations.py::TestActualThreading -v
```

### Thread Safety Guarantees
- boto3 S3 client is thread-safe (connection pooling)
- FastAPI handles concurrent requests safely
- First-writer-wins for approval conflicts
- S3 provides strong read-after-write consistency

## Compliance Test Structure

### WORM Immutability Tests (`tests/integration/test_audit_trail.py`)
Tests verify Write-Once-Read-Many (WORM) immutability:
- Deletion prevention
- Modification prevention
- Audit log immutability
- S3 configuration validation (Object Lock, Versioning, Encryption)
- Data integrity (checksums)
- Production smoke tests

Markers: `@pytest.mark.integration`, `@pytest.mark.worm`, `@pytest.mark.sox_critical`

### Audit Trail Tests (`tests/integration/test_audit_trail.py`)
Tests verify audit logging completeness:
- Audit log completeness (no gaps)
- Duplicate event prevention
- Failed operation auditing
- Modification attempt auditing

Markers: `@pytest.mark.integration`, `@pytest.mark.audit_trail`

### Concurrency Tests (`tests/integration/test_concurrent_operations.py`)
Tests verify thread safety and concurrent operation handling:
- Concurrent writes with race condition handling
- Idempotency under concurrent load
- S3 consistency guarantees

Markers: `@pytest.mark.integration`, `@pytest.mark.concurrency`

## Running Tests by Category

```bash
# Security tests only
pytest -m security -v

# SOX-critical tests (must pass for production)
pytest -m sox_critical --strict-markers -v

# WORM immutability tests
pytest -m worm -v

# All compliance tests
pytest -m "security or worm or audit_trail" -v

# Production smoke tests (run before deployment)
pytest -m production_smoke -v
```

## Troubleshooting Integration Tests

### MinIO Connection Issues
- Check Docker: `docker compose -f docker-compose.ci.yml ps`
- Check logs: `docker compose -f docker-compose.ci.yml logs minio`
- Verify endpoint: `curl http://localhost:9010/minio/health/live`

### S3 Bucket Cleanup Issues
- Buckets persist between test runs
- Clean manually: `docker compose -f docker-compose.ci.yml down -v`
- Or use clean_bucket fixture

### Rate Limiter Conflicts
- Rate limiter disabled by default in tests (conftest.py line 173-206)
- Rate limiting tests enable it temporarily
- If conflicts, check app.state.limiter_enabled

### Threading Race Condition Debugging
- Add print statements in threads (use logging instead)
- Increase timeouts: thread.join(timeout=30)
- Check for deadlocks: use threading.Timer
- Verify barrier count matches thread count

### WORM Tests Failing
- MinIO: XFAIL expected (no Object Lock support)
- Production: ALL tests must pass
- Check S3 config: get_object_lock_configuration()
- Verify versioning enabled

## Running Tests Locally

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run all tests
```bash
pytest
```

### Run tests with verbose output
```bash
pytest -v
```

### Run tests with coverage
```bash
pytest --cov=grind tests/
```

### Run a specific test file
```bash
pytest tests/integration/test_audit_trail.py
```

### Run a specific test class
```bash
pytest tests/integration/test_audit_trail.py::TestWORMImmutability
```

### Run a specific test
```bash
pytest tests/integration/test_audit_trail.py::TestWORMImmutability::test_approval_record_cannot_be_deleted
```

## Continuous Integration

Tests are run automatically on:
- Pull requests
- Commits to main branch
- Pre-deployment checks

The CI pipeline ensures:
1. All unit tests pass
2. All integration tests pass
3. All SOX-critical tests pass (100% required for deployment)
4. Code coverage meets minimum threshold

## Test Conventions

### Test File Organization
- `tests/` - Unit tests
- `tests/integration/` - Integration tests requiring external services

### Test Naming
- Test modules: `test_<feature>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<behavior>`

### Fixtures
Common fixtures for integration tests:
- `integration_client` - HTTP client for API testing
- `integration_storage_client` - S3 storage client
- `s3_config` - S3 bucket configuration

## Debugging Failed Tests

### Enable debug output
```bash
pytest -v --tb=long --capture=no
```

### Run single test with pdb
```bash
pytest tests/integration/test_audit_trail.py::TestWORMImmutability::test_approval_record_cannot_be_deleted --pdb
```

### Show print statements
```bash
pytest -s tests/integration/test_audit_trail.py
```

## Production Deployment Checklist

Before deploying to production:

1. **Run SOX-critical tests**
   ```bash
   ./scripts/run-sox-critical-tests.sh
   ```

2. **Verify all tests pass**
   ```bash
   pytest
   ```

3. **Verify code coverage**
   ```bash
   pytest --cov=grind --cov-report=html
   ```

4. **Verify specific compliance tests**
   ```bash
   pytest -m "sox_critical or security or worm or audit_trail" -v
   ```

5. **Verify production smoke tests**
   ```bash
   pytest -m production_smoke
   ```

If any SOX-critical test fails, **do not proceed with deployment**. Address the failure and re-run all compliance tests.
