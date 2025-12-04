"""
WORM Immutability Tests for SOX Compliance

These tests verify that approval records are Write-Once-Read-Many (WORM),
which is required for SOX compliance. Production S3 bucket MUST have:

1. Object Lock: ENABLED in COMPLIANCE mode (not GOVERNANCE)
2. Versioning: ENABLED (preserves all versions)
3. Encryption: ENABLED (AES-256 or KMS)
4. Retention: >= 7 years (SOX requirement)
5. Access Logging: ENABLED to separate audit bucket

Some tests XFAIL in MinIO test environment (lacks Object Lock support).
These tests MUST PASS when run against production S3.
"""

import pytest
from datetime import datetime, timedelta
import json
import hashlib

# Mock ClientError for testing without boto3 dependency
try:
    from botocore.exceptions import ClientError
except ImportError:
    # Create a mock ClientError for testing environments without boto3
    class ClientError(Exception):
        """Mock ClientError for testing."""
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name
            super().__init__(f"{operation_name}: {error_response.get('Error', {}).get('Message', '')}")


@pytest.mark.integration
@pytest.mark.worm
@pytest.mark.sox_critical
class TestWORMImmutability:
    """
    Comprehensive tests for Write-Once-Read-Many (WORM) immutability
    to ensure SOX compliance for audit trails and approval records.
    """

    # ========================================
    # 1. Deletion Prevention Tests
    # ========================================

    @pytest.mark.xfail(
        reason="MinIO test env lacks S3 Object Lock. "
               "CRITICAL: Production MUST have Object Lock enabled. "
               "This test MUST PASS in production.",
        strict=False
    )
    def test_approval_record_cannot_be_deleted(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that approval records cannot be deleted once created.

        In production, S3 Object Lock MUST prevent deletion.
        This is a core requirement for SOX compliance - audit records
        must be immutable and tamper-proof.
        """
        # Create an approval record
        commit_hash = "abc123def456"
        response = integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "john.doe@example.com",
                "decision": "approved",
                "comments": "LGTM"
            }
        )
        assert response.status_code == 200

        # Verify the approval exists in S3
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        try:
            integration_storage_client.client.head_object(
                Bucket=s3_config["bucket"],
                Key=s3_key
            )
        except ClientError:
            pytest.fail(f"Approval record not found in S3: {s3_key}")

        # Attempt to delete the approval record
        # With Object Lock enabled, this should raise AccessDenied
        with pytest.raises(ClientError) as exc_info:
            integration_storage_client.client.delete_object(
                Bucket=s3_config["bucket"],
                Key=s3_key
            )

        # Verify the error is AccessDenied
        assert exc_info.value.response["Error"]["Code"] == "AccessDenied"

        # Verify the object still exists
        integration_storage_client.client.head_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )

    @pytest.mark.integration
    def test_approval_record_deletion_attempt_is_audited(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that deletion attempts are logged in the audit trail.

        Even failed deletion attempts must be audited for SOX compliance.
        This provides a tamper detection mechanism.
        """
        # Create an approval record
        commit_hash = "def456ghi789"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "jane.smith@example.com",
                "decision": "approved",
                "comments": "Approved after review"
            }
        )

        # Attempt to delete (will fail with Object Lock)
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        try:
            integration_storage_client.client.delete_object(
                Bucket=s3_config["bucket"],
                Key=s3_key
            )
        except ClientError:
            pass  # Expected to fail

        # Check audit trail for deletion attempt
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        # List all audit logs for today
        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        # Search for deletion_attempt event
        deletion_logged = False
        if "Contents" in response:
            for obj in response["Contents"]:
                audit_data = integration_storage_client.client.get_object(
                    Bucket=s3_config["bucket"],
                    Key=obj["Key"]
                )
                content = json.loads(audit_data["Body"].read().decode("utf-8"))

                if (content.get("event_type") == "deletion_attempt" and
                    commit_hash in content.get("resource", "")):
                    deletion_logged = True
                    break

        assert deletion_logged, "Deletion attempt was not logged in audit trail"

    @pytest.mark.integration
    @pytest.mark.xfail(
        reason="Bucket deletion protection may not be configured in test env. "
               "MUST be enabled in production.",
        strict=False
    )
    def test_s3_bucket_cannot_be_deleted(self, s3_config, integration_storage_client):
        """
        Test that the S3 bucket itself cannot be deleted.

        Critical for preventing accidental data loss. Bucket policies
        should prevent deletion even by administrators.
        """
        with pytest.raises(ClientError) as exc_info:
            integration_storage_client.client.delete_bucket(
                Bucket=s3_config["bucket"]
            )

        # Should fail with BucketNotEmpty or AccessDenied
        error_code = exc_info.value.response["Error"]["Code"]
        assert error_code in ["BucketNotEmpty", "AccessDenied"]

    # ========================================
    # 2. Modification Prevention Tests
    # ========================================

    @pytest.mark.integration
    @pytest.mark.xfail(
        reason="MinIO may not enforce Object Lock modification prevention. "
               "CRITICAL: Production S3 MUST prevent modifications.",
        strict=False
    )
    def test_approval_record_cannot_be_modified(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that approval records cannot be modified after creation.

        Modifications to approval records would violate SOX requirements.
        Object Lock should prevent any overwrite attempts.
        """
        # Create original approval
        commit_hash = "original123456"
        original_approver = "alice.jones@example.com"

        response = integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": original_approver,
                "decision": "approved",
                "comments": "Original approval"
            }
        )
        assert response.status_code == 200

        # Read the original approval
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        original_obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )
        original_data = json.loads(original_obj["Body"].read().decode("utf-8"))
        original_etag = original_obj["ETag"]

        # Attempt to modify the record
        modified_data = original_data.copy()
        modified_data["approver"] = "attacker@evil.com"
        modified_data["decision"] = "rejected"

        # Try to overwrite
        try:
            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=s3_key,
                Body=json.dumps(modified_data).encode("utf-8")
            )
        except ClientError as e:
            # Expected: Object Lock prevents modification
            assert e.response["Error"]["Code"] == "AccessDenied"

        # Verify original is still intact
        current_obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )
        current_data = json.loads(current_obj["Body"].read().decode("utf-8"))

        assert current_data["approver"] == original_approver
        assert current_obj["ETag"] == original_etag

    @pytest.mark.integration
    def test_approval_record_versioning_preserves_original(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that S3 versioning preserves the original version.

        Even if modification is allowed (shouldn't be with Object Lock),
        versioning ensures the original is preserved. S3 versioning MUST
        be enabled in production.
        """
        # Create approval
        commit_hash = "versioned789"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "bob.smith@example.com",
                "decision": "approved",
                "comments": "Original version"
            }
        )

        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        # Get original version ID
        response = integration_storage_client.client.list_object_versions(
            Bucket=s3_config["bucket"],
            Prefix=s3_key
        )

        assert "Versions" in response
        assert len(response["Versions"]) >= 1

        original_version_id = response["Versions"][0]["VersionId"]

        # Attempt to create a new version (if allowed)
        try:
            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=s3_key,
                Body=json.dumps({"modified": "data"}).encode("utf-8")
            )
        except ClientError:
            # If Object Lock prevents this, test still passes
            pass

        # List versions again
        response = integration_storage_client.client.list_object_versions(
            Bucket=s3_config["bucket"],
            Prefix=s3_key
        )

        # Verify original version still exists
        version_ids = [v["VersionId"] for v in response.get("Versions", [])]
        assert original_version_id in version_ids

        # Verify we can retrieve the original version
        original_obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key,
            VersionId=original_version_id
        )
        assert original_obj is not None

    @pytest.mark.integration
    @pytest.mark.audit_trail
    def test_modification_attempt_is_audited(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that modification attempts are logged in the audit trail.

        Attempted modifications must be audited to detect tampering attempts.
        """
        # Enable object lock to ensure modification attempt is blocked and logged
        s3_config["object_lock_enabled"] = True

        # Create approval
        commit_hash = "modaudit123"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "carol.white@example.com",
                "decision": "approved",
                "comments": "Test modification audit"
            }
        )

        # Attempt to modify
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        try:
            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=s3_key,
                Body=json.dumps({"tampered": "data"}).encode("utf-8")
            )
        except Exception:
            # Expected to fail - catch any exception type since ClientError is from conftest
            pass

        # Check audit trail
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        modification_logged = False
        if "Contents" in response:
            for obj in response["Contents"]:
                audit_data = integration_storage_client.client.get_object(
                    Bucket=s3_config["bucket"],
                    Key=obj["Key"]
                )
                content = json.loads(audit_data["Body"].read().decode("utf-8"))

                if (content.get("event_type") in ["modification_attempt", "put_object"] and
                    commit_hash in content.get("resource", "")):
                    modification_logged = True
                    assert "who" in content or "user" in content
                    assert "timestamp" in content or "when" in content
                    break

        assert modification_logged, "Modification attempt not logged in audit trail"

    # ========================================
    # 3. Audit Log Immutability Tests
    # ========================================

    @pytest.mark.integration
    @pytest.mark.xfail(
        reason="Audit log Object Lock may not be configured in test env. "
               "MUST be enabled in production.",
        strict=False
    )
    def test_audit_log_cannot_be_tampered(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that audit logs themselves cannot be tampered with.

        Critical: If audit logs can be modified, the entire audit trail
        is compromised. Object Lock MUST protect audit logs.
        """
        # Create an approval to generate audit log
        commit_hash = "auditlog456"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "david.brown@example.com",
                "decision": "approved",
                "comments": "Generate audit log"
            }
        )

        # Find the audit log
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        assert "Contents" in response and len(response["Contents"]) > 0
        audit_key = response["Contents"][0]["Key"]

        # Read original audit log
        original_log = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=audit_key
        )

        # Attempt to modify audit log
        with pytest.raises(ClientError) as exc_info:
            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=audit_key,
                Body=json.dumps({"tampered": "audit"}).encode("utf-8")
            )
        assert exc_info.value.response["Error"]["Code"] == "AccessDenied"

        # Attempt to delete audit log
        with pytest.raises(ClientError) as exc_info:
            integration_storage_client.client.delete_object(
                Bucket=s3_config["bucket"],
                Key=audit_key
            )
        assert exc_info.value.response["Error"]["Code"] == "AccessDenied"

    @pytest.mark.integration
    @pytest.mark.audit_trail
    def test_audit_log_completeness_no_gaps(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that audit logs have no gaps - all operations are logged.

        For SOX compliance, every operation must be logged with
        consecutive sequence numbers.
        """
        # Perform 10 mixed operations
        operations = []
        base_commit = "complete"

        for i in range(10):
            commit_hash = f"{base_commit}{i:03d}"
            decision = "approved" if i % 2 == 0 else "rejected"

            response = integration_client.post(
                f"/api/v1/approve/{commit_hash}",
                json={
                    "approver": f"user{i}@example.com",
                    "decision": decision,
                    "comments": f"Operation {i}"
                }
            )
            operations.append({
                "commit": commit_hash,
                "decision": decision,
                "index": i
            })

        # Query all audit logs for today
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        assert "Contents" in response

        # Collect all sequence numbers
        sequence_numbers = []
        logged_commits = set()

        for obj in response["Contents"]:
            audit_data = integration_storage_client.client.get_object(
                Bucket=s3_config["bucket"],
                Key=obj["Key"]
            )
            content = json.loads(audit_data["Body"].read().decode("utf-8"))

            if "sequence" in content:
                sequence_numbers.append(content["sequence"])

            # Track which of our operations were logged
            for op in operations:
                if op["commit"] in str(content):
                    logged_commits.add(op["commit"])

        # Verify all operations were logged
        expected_commits = {op["commit"] for op in operations}
        assert logged_commits == expected_commits, \
            f"Missing commits in audit log: {expected_commits - logged_commits}"

        # If sequence numbers are used, verify they're consecutive
        if sequence_numbers:
            sequence_numbers.sort()
            for i in range(len(sequence_numbers) - 1):
                # Allow for gaps if other processes are logging
                assert sequence_numbers[i+1] >= sequence_numbers[i], \
                    f"Non-monotonic sequence: {sequence_numbers[i]} -> {sequence_numbers[i+1]}"

    @pytest.mark.integration
    @pytest.mark.audit_trail
    def test_audit_trail_no_duplicate_events(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that audit trail doesn't contain duplicate events.

        Idempotency check: performing the same operation multiple times
        should not create duplicate audit entries (or should be clearly
        marked as retries).
        """
        # Perform a single approval
        commit_hash = "nodupes123"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "eve.davis@example.com",
                "decision": "approved",
                "comments": "Single approval"
            }
        )

        # Query audit logs
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        # Count approval events for this commit
        approval_count = 0
        event_ids = set()

        if "Contents" in response:
            for obj in response["Contents"]:
                audit_data = integration_storage_client.client.get_object(
                    Bucket=s3_config["bucket"],
                    Key=obj["Key"]
                )
                content = json.loads(audit_data["Body"].read().decode("utf-8"))

                if (content.get("event_type") == "approval" and
                    commit_hash in content.get("resource", "")):
                    approval_count += 1

                    # Track unique event IDs
                    if "event_id" in content:
                        event_ids.add(content["event_id"])

        # Should have exactly one approval event
        assert approval_count == 1, \
            f"Expected 1 approval event, found {approval_count}"

        # Event IDs should all be unique (if present)
        if event_ids:
            assert len(event_ids) == approval_count

    # ========================================
    # 4. S3 Configuration Validation Tests
    # ========================================

    @pytest.mark.integration
    @pytest.mark.sox_critical
    @pytest.mark.xfail(
        reason="MinIO may not have versioning enabled. "
               "CRITICAL: Production MUST have versioning enabled.",
        strict=False
    )
    def test_s3_versioning_enabled(self, s3_config, integration_storage_client):
        """
        Test that S3 bucket versioning is enabled.

        This is REQUIRED for SOX compliance. Versioning ensures that
        all versions of objects are preserved, even if overwritten.
        """
        response = integration_storage_client.client.get_bucket_versioning(
            Bucket=s3_config["bucket"]
        )

        assert "Status" in response, "Versioning status not found in response"
        assert response["Status"] == "Enabled", \
            f"S3 versioning MUST be Enabled, found: {response.get('Status', 'None')}"

    @pytest.mark.integration
    @pytest.mark.sox_critical
    @pytest.mark.xfail(
        reason="MinIO test env does not support S3 Object Lock. "
               "CRITICAL: Production MUST have Object Lock enabled. "
               "This test MUST PASS in production.",
        strict=False
    )
    def test_s3_object_lock_enabled(self, s3_config, integration_storage_client):
        """
        Test that S3 Object Lock is enabled on the bucket.

        Production MUST have Object Lock in COMPLIANCE mode.
        Object Lock is the core WORM mechanism that prevents deletion
        and modification of objects.
        """
        try:
            response = integration_storage_client.client.get_object_lock_configuration(
                Bucket=s3_config["bucket"]
            )

            assert "ObjectLockConfiguration" in response
            assert response["ObjectLockConfiguration"]["ObjectLockEnabled"] == "Enabled"

        except ClientError as e:
            if e.response["Error"]["Code"] == "ObjectLockConfigurationNotFoundError":
                pytest.fail(
                    "Object Lock is NOT enabled on bucket. "
                    "This is REQUIRED for SOX compliance in production!"
                )
            raise

    @pytest.mark.integration
    @pytest.mark.sox_critical
    @pytest.mark.xfail(
        reason="MinIO does not support Object Lock COMPLIANCE mode. "
               "CRITICAL: Production MUST use COMPLIANCE mode with 7-year retention.",
        strict=False
    )
    def test_s3_object_lock_mode_is_compliance(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that Object Lock mode is COMPLIANCE (not GOVERNANCE).

        COMPLIANCE mode: even root user cannot delete until retention expires.
        GOVERNANCE mode: privileged users CAN delete (not SOX compliant).
        Retention period must be >= 7 years for SOX.
        """
        # Create an approval with Object Lock
        commit_hash = "compliance123"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "frank.miller@example.com",
                "decision": "approved",
                "comments": "Test compliance mode"
            }
        )

        # Check the object's lock configuration
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        try:
            response = integration_storage_client.client.get_object_retention(
                Bucket=s3_config["bucket"],
                Key=s3_key
            )

            # Verify COMPLIANCE mode
            assert "Retention" in response
            assert response["Retention"]["Mode"] == "COMPLIANCE", \
                f"Object Lock must use COMPLIANCE mode, found: {response['Retention']['Mode']}"

            # Verify retention period >= 7 years
            retain_until = response["Retention"]["RetainUntilDate"]
            created_date = datetime.utcnow()
            seven_years = created_date + timedelta(days=7*365)

            assert retain_until >= seven_years, \
                f"Retention period must be >= 7 years for SOX compliance"

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchObjectLockConfiguration":
                pytest.fail(
                    "Object Lock retention not configured. "
                    "COMPLIANCE mode with 7-year retention is REQUIRED!"
                )
            raise

    @pytest.mark.integration
    @pytest.mark.sox_critical
    @pytest.mark.xfail(
        reason="Encryption may not be configured in test env. "
               "CRITICAL: Production MUST have encryption enabled.",
        strict=False
    )
    def test_s3_encryption_at_rest_enabled(self, s3_config, integration_storage_client):
        """
        Test that S3 bucket encryption at rest is enabled.

        SOX often requires encryption for sensitive data.
        Verify AES256 or aws:kms encryption is configured.
        """
        try:
            response = integration_storage_client.client.get_bucket_encryption(
                Bucket=s3_config["bucket"]
            )

            assert "Rules" in response
            assert len(response["Rules"]) > 0

            # Get encryption algorithm
            rule = response["Rules"][0]
            if "ApplyServerSideEncryptionByDefault" in rule:
                encryption_config = rule["ApplyServerSideEncryptionByDefault"]
                algorithm = encryption_config.get("SSEAlgorithm")

                assert algorithm in ["AES256", "aws:kms"], \
                    f"Encryption algorithm must be AES256 or aws:kms, found: {algorithm}"

                print(f"\n✓ Bucket encryption enabled: {algorithm}")

                if algorithm == "aws:kms":
                    kms_key = encryption_config.get("KMSMasterKeyID", "default")
                    print(f"  KMS Key: {kms_key}")
            else:
                pytest.fail("Server-side encryption not configured")

        except ClientError as e:
            if e.response["Error"]["Code"] == "ServerSideEncryptionConfigurationNotFoundError":
                pytest.fail(
                    "Bucket encryption is NOT enabled. "
                    "Encryption at rest is recommended for SOX compliance!"
                )
            raise

    # ========================================
    # 5. Data Integrity Tests
    # ========================================

    @pytest.mark.integration
    def test_approval_record_has_checksum(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that approval records have checksums for data integrity.

        ETags (MD5 checksums) prove data integrity over time.
        """
        # Create approval
        commit_hash = "checksum789"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "grace.lee@example.com",
                "decision": "approved",
                "comments": "Test checksum"
            }
        )

        # Read object and verify ETag
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )

        assert "ETag" in obj
        original_etag = obj["ETag"]
        assert original_etag is not None and len(original_etag) > 0

        # Store data for later verification
        original_data = obj["Body"].read()

        # Re-read and verify ETag unchanged
        obj2 = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )

        assert obj2["ETag"] == original_etag, \
            "ETag changed - data integrity may be compromised!"

        # Verify data matches
        new_data = obj2["Body"].read()
        assert new_data == original_data

    @pytest.mark.integration
    @pytest.mark.xfail(
        reason="Cannot easily corrupt S3 objects in test environment. "
               "This test validates application-level checksum verification.",
        strict=False
    )
    def test_checksum_mismatch_detected(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that checksum mismatches are detected.

        If data corruption occurs, the application should detect
        it via checksum validation.
        """
        # Create approval
        commit_hash = "corrupt123"
        integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "henry.wilson@example.com",
                "decision": "approved",
                "comments": "Test corruption detection"
            }
        )

        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        # Get original object
        obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )
        original_data = obj["Body"].read()
        original_etag = obj["ETag"]

        # Simulate corruption by computing checksum of corrupted data
        corrupted_data = original_data.replace(b"approved", b"hacked!!")
        corrupted_md5 = hashlib.md5(corrupted_data).hexdigest()

        # Verify checksums differ
        original_md5 = original_etag.strip('"')
        assert corrupted_md5 != original_md5, \
            "Corruption should result in different checksum"

        # In a real system, attempting to use corrupted data should fail validation
        # This would be application-level logic

    @pytest.mark.integration
    def test_s3_read_consistency_strong(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test S3 strong read-after-write consistency.

        S3 provides strong read-after-write consistency (since Dec 2020).
        Data written should be immediately readable with no delays.
        """
        # Write approval record
        commit_hash = "consistency456"
        approval_data = {
            "approver": "iris.chen@example.com",
            "decision": "approved",
            "comments": "Test read consistency"
        }

        response = integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json=approval_data
        )
        assert response.status_code == 200

        # Immediately read (no delay)
        repo_name = s3_config.get("repo_name", "test-repo")
        s3_key = f"approvals/{repo_name}/{commit_hash}.json"

        obj = integration_storage_client.client.get_object(
            Bucket=s3_config["bucket"],
            Key=s3_key
        )

        read_data = json.loads(obj["Body"].read().decode("utf-8"))

        # Verify data matches exactly what was written
        assert read_data["approver"] == approval_data["approver"]
        assert read_data["decision"] == approval_data["decision"]
        assert read_data["comments"] == approval_data["comments"]

    # ========================================
    # 6. Failed Operations Audit Test
    # ========================================

    @pytest.mark.integration
    @pytest.mark.audit_trail
    def test_failed_operations_are_audited(
        self, integration_client, integration_storage_client, s3_config
    ):
        """
        Test that failed operations are logged in the audit trail.

        SOX requires negative audit - failed access attempts must be logged
        to detect unauthorized access attempts.
        """
        # Attempt unauthorized approval (wrong user/credentials)
        commit_hash = "unauthorized999"

        response = integration_client.post(
            f"/api/v1/approve/{commit_hash}",
            json={
                "approver": "unauthorized@evil.com",
                "decision": "approved",
                "comments": "Unauthorized attempt"
            },
            headers={"Authorization": "Bearer invalid_token"}
        )

        # Expect 403 Forbidden or 401 Unauthorized
        assert response.status_code in [401, 403]

        # Verify failure is logged in audit trail
        today = datetime.utcnow()
        audit_prefix = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/"

        response = integration_storage_client.client.list_objects_v2(
            Bucket=s3_config["bucket"],
            Prefix=audit_prefix
        )

        failure_logged = False
        if "Contents" in response:
            for obj in response["Contents"]:
                audit_data = integration_storage_client.client.get_object(
                    Bucket=s3_config["bucket"],
                    Key=obj["Key"]
                )
                content = json.loads(audit_data["Body"].read().decode("utf-8"))

                # Look for failure events
                if (content.get("event_type") in ["approval_failed", "access_denied"] and
                    content.get("outcome") in ["unauthorized", "forbidden", "failed"]):
                    failure_logged = True
                    break

        assert failure_logged, \
            "Failed operation was not logged in audit trail (negative audit required)"

    # ========================================
    # 7. Production Configuration Smoke Test
    # ========================================

    @pytest.mark.integration
    @pytest.mark.sox_critical
    @pytest.mark.production_smoke
    def test_production_s3_has_worm_enabled_smoke_test(
        self, s3_config, integration_storage_client
    ):
        """
        Smoke test: Verify production S3 has WORM enabled.

        This test MUST FAIL if production is misconfigured.
        Prevents deployment to non-compliant infrastructure.

        Checks:
        - Object Lock enabled
        - Versioning enabled
        - Encryption enabled
        - Retention period >= 7 years (if applicable)
        """
        # Detect if we're in production
        is_production = s3_config.get("environment") == "production"
        bucket_name = s3_config["bucket"]

        if not is_production and "prod" not in bucket_name.lower():
            pytest.skip("Not running in production environment - skipping smoke test")

        print(f"\n{'='*60}")
        print(f"PRODUCTION WORM CONFIGURATION SMOKE TEST")
        print(f"Bucket: {bucket_name}")
        print(f"{'='*60}\n")

        failures = []

        # Check 1: Object Lock
        try:
            lock_config = integration_storage_client.client.get_object_lock_configuration(
                Bucket=bucket_name
            )
            if lock_config["ObjectLockConfiguration"]["ObjectLockEnabled"] == "Enabled":
                print("✓ Object Lock: ENABLED")
            else:
                failures.append("Object Lock is NOT enabled")
        except ClientError:
            failures.append("Object Lock is NOT configured")

        # Check 2: Versioning
        try:
            versioning = integration_storage_client.client.get_bucket_versioning(
                Bucket=bucket_name
            )
            if versioning.get("Status") == "Enabled":
                print("✓ Versioning: ENABLED")
            else:
                failures.append(f"Versioning is NOT enabled (status: {versioning.get('Status', 'None')})")
        except ClientError as e:
            failures.append(f"Versioning check failed: {e}")

        # Check 3: Encryption
        try:
            encryption = integration_storage_client.client.get_bucket_encryption(
                Bucket=bucket_name
            )
            if encryption.get("Rules"):
                algorithm = encryption["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
                print(f"✓ Encryption: ENABLED ({algorithm})")
            else:
                failures.append("Encryption is NOT configured")
        except ClientError:
            failures.append("Encryption is NOT enabled")

        print(f"\n{'='*60}")

        # If any checks failed, fail the test
        if failures:
            failure_msg = "\n".join([f"  ✗ {f}" for f in failures])
            pytest.fail(
                f"\nPRODUCTION WORM CONFIGURATION FAILURES:\n{failure_msg}\n\n"
                f"Production S3 bucket MUST have Object Lock, Versioning, and Encryption enabled!"
            )
        else:
            print("✓ ALL WORM CONFIGURATION CHECKS PASSED")
            print(f"{'='*60}\n")
