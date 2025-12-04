"""Fixtures for integration tests - SOX compliance WORM immutability tests."""

import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime
import json


# Import ClientError from botocore or create a mock
try:
    from botocore.exceptions import ClientError
except ImportError:
    # Mock ClientError for testing without boto3 dependency
    class ClientError(Exception):
        """Mock ClientError for testing."""
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name
            super().__init__(f"{operation_name}: {error_response.get('Error', {}).get('Message', '')}")


@pytest.fixture
def s3_config():
    """Mock S3 configuration for testing."""
    return {
        "bucket": "test-sox-compliance-bucket",
        "region": "us-east-1",
        "repo_name": "test-repo",
        "environment": "test"
    }


@pytest.fixture
def integration_storage_client(s3_config):
    """
    Mock storage client that simulates S3 operations.

    In a real implementation, this would be a boto3 S3 client.
    For this demo, we create a mock that simulates WORM behavior.
    """
    import threading

    mock_client = MagicMock()

    # Simulate in-memory S3 storage
    storage = {}
    versions = {}  # Track object versions
    storage_lock = threading.Lock()  # Thread-safe access to storage

    def mock_put_object(Bucket, Key, Body, **kwargs):
        """Simulate putting an object to S3."""
        with storage_lock:
            is_modification = Key in storage
            is_audit_log = Key.startswith("audit/")

            # With Object Lock, this should fail for existing objects (except audit logs)
            if is_modification and s3_config.get("object_lock_enabled") and not is_audit_log:
                # Log modification attempt
                today = datetime.utcnow()
                audit_key = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/modification_attempt_{hash(Key) % 10000}.json"

                audit_entry = {
                    "event_type": "modification_attempt",
                    "resource": Key,
                    "timestamp": datetime.utcnow().isoformat(),
                    "outcome": "denied",
                    "who": "unknown",
                    "when": datetime.utcnow().isoformat()
                }

                storage[audit_key] = {
                    "Body": json_module.dumps(audit_entry).encode("utf-8"),
                    "ETag": '"' + str(hash(audit_key))[-10:] + '"',
                    "LastModified": datetime.utcnow(),
                    "ContentLength": len(json_module.dumps(audit_entry))
                }

                error = {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "Object Lock prevents modification"
                    }
                }
                raise ClientError(error, "PutObject")

            # Store object
            storage[Key] = {
                "Body": Body if isinstance(Body, bytes) else Body.encode("utf-8"),
                "ETag": '"' + str(hash(Body))[-10:] + '"',
                "LastModified": datetime.utcnow(),
                "ContentLength": len(Body) if isinstance(Body, bytes) else len(Body.encode("utf-8"))
            }

            # Track version
            if Key not in versions:
                versions[Key] = []
            versions[Key].append({
                "VersionId": f"v{len(versions[Key]) + 1}",
                "ETag": storage[Key]["ETag"],
                "IsLatest": True
            })

            # Update previous versions
            for v in versions[Key][:-1]:
                v["IsLatest"] = False

            return {
                "ETag": storage[Key]["ETag"],
                "VersionId": versions[Key][-1]["VersionId"]
            }

    def mock_get_object(Bucket, Key, VersionId=None, **kwargs):
        """Simulate getting an object from S3."""
        with storage_lock:
            if Key not in storage:
                error = {
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": f"The specified key does not exist: {Key}"
                    }
                }
                raise ClientError(error, "GetObject")

            obj = storage[Key]
            body_mock = MagicMock()
            body_mock.read.return_value = obj["Body"]

            return {
                "Body": body_mock,
                "ETag": obj["ETag"],
                "LastModified": obj["LastModified"],
                "ContentLength": obj["ContentLength"]
            }

    def mock_head_object(Bucket, Key, **kwargs):
        """Simulate HEAD request to check if object exists."""
        with storage_lock:
            if Key not in storage:
                error = {
                    "Error": {
                        "Code": "404",
                        "Message": f"Not Found: {Key}"
                    }
                }
                raise ClientError(error, "HeadObject")

            return {
                "ETag": storage[Key]["ETag"],
                "LastModified": storage[Key]["LastModified"],
                "ContentLength": storage[Key]["ContentLength"]
            }

    def mock_delete_object(Bucket, Key, **kwargs):
        """Simulate deleting an object (should fail with Object Lock)."""
        with storage_lock:
            # Log deletion attempt to audit trail
            today = datetime.utcnow()
            audit_key = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/deletion_attempt_{hash(Key) % 10000}.json"

            audit_entry = {
                "event_type": "deletion_attempt",
                "resource": Key,
                "timestamp": datetime.utcnow().isoformat(),
                "outcome": "denied" if s3_config.get("object_lock_enabled") else "success"
            }

            storage[audit_key] = {
                "Body": json_module.dumps(audit_entry).encode("utf-8"),
                "ETag": '"' + str(hash(audit_key))[-10:] + '"',
                "LastModified": datetime.utcnow(),
                "ContentLength": len(json_module.dumps(audit_entry))
            }

            if s3_config.get("object_lock_enabled"):
                error = {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "Object Lock prevents deletion"
                    }
                }
                raise ClientError(error, "DeleteObject")

            # Without Object Lock, deletion succeeds (for testing)
            if Key in storage:
                del storage[Key]

            return {"DeleteMarker": True}

    def mock_list_objects_v2(Bucket, Prefix="", **kwargs):
        """Simulate listing objects in S3."""
        with storage_lock:
            matching_keys = [k for k in storage.keys() if k.startswith(Prefix)]

            if not matching_keys:
                return {}

            contents = []
            for key in matching_keys:
                contents.append({
                    "Key": key,
                    "LastModified": storage[key]["LastModified"],
                    "ETag": storage[key]["ETag"],
                    "Size": storage[key]["ContentLength"]
                })

            return {"Contents": contents}

    def mock_list_object_versions(Bucket, Prefix="", **kwargs):
        """Simulate listing object versions."""
        with storage_lock:
            matching_keys = [k for k in versions.keys() if k.startswith(Prefix)]

            if not matching_keys:
                return {}

            all_versions = []
            for key in matching_keys:
                for version_info in versions[key]:
                    all_versions.append({
                        "Key": key,
                        "VersionId": version_info["VersionId"],
                        "IsLatest": version_info["IsLatest"],
                        "ETag": version_info["ETag"],
                        "LastModified": datetime.utcnow()
                    })

            return {"Versions": all_versions}

    def mock_get_bucket_versioning(Bucket, **kwargs):
        """Simulate getting bucket versioning status."""
        if s3_config.get("versioning_enabled", False):
            return {"Status": "Enabled"}
        return {}

    def mock_get_object_lock_configuration(Bucket, **kwargs):
        """Simulate getting Object Lock configuration."""
        if s3_config.get("object_lock_enabled", False):
            return {
                "ObjectLockConfiguration": {
                    "ObjectLockEnabled": "Enabled",
                    "Rule": {
                        "DefaultRetention": {
                            "Mode": "COMPLIANCE",
                            "Days": 2555  # 7 years
                        }
                    }
                }
            }

        error = {
            "Error": {
                "Code": "ObjectLockConfigurationNotFoundError",
                "Message": "Object Lock configuration not found"
            }
        }
        raise ClientError(error, "GetObjectLockConfiguration")

    def mock_get_object_retention(Bucket, Key, **kwargs):
        """Simulate getting object retention settings."""
        if not s3_config.get("object_lock_enabled", False):
            error = {
                "Error": {
                    "Code": "NoSuchObjectLockConfiguration",
                    "Message": "Object Lock not configured"
                }
            }
            raise ClientError(error, "GetObjectRetention")

        from datetime import timedelta
        return {
            "Retention": {
                "Mode": "COMPLIANCE",
                "RetainUntilDate": datetime.utcnow() + timedelta(days=2555)
            }
        }

    def mock_get_bucket_encryption(Bucket, **kwargs):
        """Simulate getting bucket encryption configuration."""
        if s3_config.get("encryption_enabled", False):
            return {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            }

        error = {
            "Error": {
                "Code": "ServerSideEncryptionConfigurationNotFoundError",
                "Message": "Encryption configuration not found"
            }
        }
        raise ClientError(error, "GetBucketEncryption")

    def mock_delete_bucket(Bucket, **kwargs):
        """Simulate bucket deletion (should fail)."""
        error = {
            "Error": {
                "Code": "BucketNotEmpty",
                "Message": "The bucket you tried to delete is not empty"
            }
        }
        raise ClientError(error, "DeleteBucket")

    # Wire up the mock client
    mock_client.put_object = Mock(side_effect=mock_put_object)
    mock_client.get_object = Mock(side_effect=mock_get_object)
    mock_client.head_object = Mock(side_effect=mock_head_object)
    mock_client.delete_object = Mock(side_effect=mock_delete_object)
    mock_client.list_objects_v2 = Mock(side_effect=mock_list_objects_v2)
    mock_client.list_object_versions = Mock(side_effect=mock_list_object_versions)
    mock_client.get_bucket_versioning = Mock(side_effect=mock_get_bucket_versioning)
    mock_client.get_object_lock_configuration = Mock(side_effect=mock_get_object_lock_configuration)
    mock_client.get_object_retention = Mock(side_effect=mock_get_object_retention)
    mock_client.get_bucket_encryption = Mock(side_effect=mock_get_bucket_encryption)
    mock_client.delete_bucket = Mock(side_effect=mock_delete_bucket)

    # Create a wrapper that exposes the client
    wrapper = MagicMock()
    wrapper.client = mock_client
    wrapper.put_approval = Mock(side_effect=lambda data, key: mock_put_object(
        Bucket=s3_config["bucket"],
        Key=key,
        Body=json.dumps(data).encode("utf-8")
    ))

    return wrapper


@pytest.fixture
def integration_client(integration_storage_client, s3_config):
    """
    Mock API client for approval operations.

    Simulates the approval API that writes to S3.
    """
    mock_client = MagicMock()

    def mock_post(url, json=None, headers=None, **kwargs):
        """Simulate POST request to approval API."""
        # Extract commit hash from URL first
        commit_hash = None
        if "/api/v1/approve/" in url:
            commit_hash = url.split("/")[-1]

        # Check for unauthorized access
        if headers and "Authorization" in headers:
            auth_header = headers["Authorization"]
            if "invalid" in auth_header.lower():
                # Log failed auth attempt
                today = datetime.utcnow()
                audit_key = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/approval_failed_{hash(commit_hash or 'unknown') % 10000}.json"

                audit_entry = {
                    "event_type": "approval_failed",
                    "outcome": "unauthorized",
                    "resource": f"/api/v1/approve/{commit_hash}" if commit_hash else url,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": "Invalid authorization token"
                }

                integration_storage_client.client.put_object(
                    Bucket=s3_config["bucket"],
                    Key=audit_key,
                    Body=json_module.dumps(audit_entry).encode("utf-8")
                )

                response = MagicMock()
                response.status_code = 401
                response.json.return_value = {"error": "Unauthorized"}
                return response

        # Extract commit hash from URL
        if "/api/v1/approve/" in url and commit_hash:

            # Create approval record in S3
            repo_name = s3_config["repo_name"]
            s3_key = f"approvals/{repo_name}/{commit_hash}.json"

            approval_data = {
                "commit": commit_hash,
                "approver": json.get("approver"),
                "decision": json.get("decision"),
                "comments": json.get("comments"),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Store in S3
            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=s3_key,
                Body=json_module.dumps(approval_data).encode("utf-8")
            )

            # Create audit log entry
            today = datetime.utcnow()
            audit_key = f"audit/{today.year:04d}/{today.month:02d}/{today.day:02d}/approval_{commit_hash}.json"

            audit_entry = {
                "event_type": "approval",
                "resource": s3_key,
                "commit": commit_hash,
                "approver": json.get("approver"),
                "decision": json.get("decision"),
                "timestamp": approval_data["timestamp"],
                "event_id": f"evt_{hash(commit_hash)}"
            }

            integration_storage_client.client.put_object(
                Bucket=s3_config["bucket"],
                Key=audit_key,
                Body=json_module.dumps(audit_entry).encode("utf-8")
            )

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = approval_data
            return response

        # Default response
        response = MagicMock()
        response.status_code = 404
        return response

    mock_client.post = Mock(side_effect=mock_post)

    return mock_client


# Need to import json module for use in fixtures
import json as json_module


# Add module-level marker configuration
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "sox_critical: mark test as critical for SOX compliance"
    )
