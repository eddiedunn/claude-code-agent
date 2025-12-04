# Integration Tests

## Test Files

Existing files (keep as-is):
- test_storage_integration.py - S3 CRUD operations
- test_auth_integration.py - Auth header validation
- test_e2e_workflows.py - Complete approval/rejection flows
- test_bitbucket_integration.py - Bitbucket API interactions
- test_mattermost_integration.py - Notification workflows
- test_pipeline_integration.py - CI/CD pipeline endpoints
- test_ownership_integration.py - Authorization with config files
- test_ui_integration.py - Web UI rendering
- test_multi_environment.py - Environment-specific logic
- test_audit_trail.py - Audit logging (now includes WORM tests)
- test_concurrent_operations.py - Race conditions (now includes threading tests)

New test files:
- **test_security_controls.py** (30-35 tests)
  - Access control: authentication, authorization, privilege escalation
  - Rate limiting: per-user limits on critical endpoints
  - DOS prevention: large payloads, resource exhaustion
  - Input validation: XSS, path traversal, SQL injection
  - Security headers: HTTP security headers validation

New test classes:
- **test_audit_trail.py::TestWORMImmutability** (12-15 tests)
  - Deletion prevention tests
  - Modification prevention tests
  - Audit log immutability
  - S3 configuration validation (Object Lock, versioning)
  - Data integrity (checksums, consistency)

- **test_concurrent_operations.py::TestActualThreading** (12-15 tests)
  - Basic threading and race conditions
  - Idempotency under concurrency
  - S3 consistency guarantees
  - Resource exhaustion handling

## Critical SOX Compliance Tests

### Why These Tests Matter
SOX (Sarbanes-Oxley) compliance requires immutable audit trails.
Our service stores approval decisions in S3 with WORM (Write Once Read Many).
These tests prove records cannot be tampered with.

### TestWORMImmutability (SOX-Critical)

Located: tests/integration/test_audit_trail.py::TestWORMImmutability

Tests verify:
1. Approval records cannot be deleted
2. Approval records cannot be modified
3. Audit logs are tamper-proof
4. S3 bucket has correct WORM configuration
5. Data integrity is maintained (checksums)

**CRITICAL**: These tests MUST pass in production for SOX compliance.

### Running SOX-Critical Tests
```bash
# All SOX-critical tests
pytest -m sox_critical -v

# WORM immutability tests
pytest tests/integration/test_audit_trail.py::TestWORMImmutability -v

# Production smoke tests (run before deployment)
pytest -m production_smoke -v

# Using convenience script
./scripts/run-sox-critical-tests.sh
```

## Production S3 Configuration

### Required Settings (CRITICAL for SOX)

Production S3 bucket MUST have:

1. **Object Lock: COMPLIANCE mode**
   ```bash
   aws s3api put-object-lock-configuration \
     --bucket compliance-approvals \
     --object-lock-configuration '{
       "ObjectLockEnabled": "Enabled",
       "Rule": {
         "DefaultRetention": {
           "Mode": "COMPLIANCE",
           "Years": 7
         }
       }
     }'
   ```

2. **Versioning: Enabled**
   ```bash
   aws s3api put-bucket-versioning \
     --bucket compliance-approvals \
     --versioning-configuration Status=Enabled
   ```

3. **Encryption: AES-256 or KMS**
   ```bash
   aws s3api put-bucket-encryption \
     --bucket compliance-approvals \
     --server-side-encryption-configuration '{
       "Rules": [{
         "ApplyServerSideEncryptionByDefault": {
           "SSEAlgorithm": "AES256"
         }
       }]
     }'
   ```

4. **Access Logging: Enabled**
   ```bash
   aws s3api put-bucket-logging \
     --bucket compliance-approvals \
     --bucket-logging-status '{
       "LoggingEnabled": {
         "TargetBucket": "compliance-audit-logs",
         "TargetPrefix": "s3-access/"
       }
     }'
   ```

5. **IAM Policy: Least Privilege**
   - Service role: write-only to approvals/ prefix
   - Auditors: read-only to all prefixes
   - No one: delete permissions

### Verifying Configuration
```bash
# Check Object Lock
aws s3api get-object-lock-configuration --bucket compliance-approvals
# Expected: ObjectLockEnabled=Enabled, Mode=COMPLIANCE, Years=7

# Check Versioning
aws s3api get-bucket-versioning --bucket compliance-approvals
# Expected: Status=Enabled

# Check Encryption
aws s3api get-bucket-encryption --bucket compliance-approvals
# Expected: SSEAlgorithm=AES256 or aws:kms

# Check Logging
aws s3api get-bucket-logging --bucket compliance-approvals
# Expected: TargetBucket set to audit log bucket
```

### MinIO vs Production

| Feature | MinIO (Test) | Production S3 | Tests |
|---------|--------------|---------------|-------|
| Object Lock | ❌ Not supported | ✅ REQUIRED | XFAIL in MinIO |
| Versioning | ✅ Supported | ✅ REQUIRED | Pass in both |
| Encryption | ✅ Supported | ✅ REQUIRED | Pass in both |
| Retention | ❌ Not enforced | ✅ 7 years | XFAIL in MinIO |
| Access Logging | ❌ Limited | ✅ REQUIRED | Not tested |

### Why Some Tests XFAIL in MinIO
MinIO (our test environment) does not support S3 Object Lock.
Tests verify behavior but are expected to fail (XFAIL).

In production with real S3, these tests MUST pass 100%.

## Test Statistics

Total integration tests: ~100+

By category:
- Storage operations: 15 tests
- Authentication/Authorization: 20 tests
- Security controls: 30-35 tests (NEW)
- WORM immutability: 12-15 tests (NEW)
- Concurrency: 12-15 tests (NEW)
- End-to-end workflows: 25 tests
- External integrations: 20 tests

Coverage target: 80%+ overall, 95%+ for SOX-critical modules

## Running Tests

### All Integration Tests
```bash
# Using Docker Compose
docker compose -f docker-compose.ci.yml run --rm test

# With coverage
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest tests/integration/ \
  --cov=compliance_service \
  --cov-report=html
```

### By Category
```bash
# Security tests only
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest -m security -v

# SOX-critical tests only
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest -m sox_critical -v

# Concurrency tests only
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest -m concurrency -v
```

### Specific Test Files
```bash
# Security controls
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest tests/integration/test_security_controls.py -v

# WORM immutability
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest tests/integration/test_audit_trail.py::TestWORMImmutability -v

# Threading tests
docker compose -f docker-compose.ci.yml run --rm test \
  uv run pytest tests/integration/test_concurrent_operations.py::TestActualThreading -v
```
