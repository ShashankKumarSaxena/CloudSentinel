from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import boto3
from botocore.stub import Stubber

from backend.app.collectors.aws import collect_aws, public_storage
from backend.app.collectors.azure import collect_azure, public_container, rule_ports
from backend.app.collectors.gcp import collect_gcp, public_bucket, firewall_ports
from backend.app.collectors.base import CollectionError, RestClient, local_token
from backend.app.models import CollectionRequest


class MappingTest(unittest.TestCase):
    def test_mounted_token_is_read_locally_without_invoking_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token'
            path.write_text('test-only-token\n')
            with patch.dict(os.environ, {'TEST_TOKEN_FILE': str(path)}), patch('backend.app.collectors.base.cli_token') as cli:
                self.assertEqual(local_token('TEST_TOKEN_FILE', ['unused']), 'test-only-token')
                cli.assert_not_called()

    def test_invalid_mounted_tokens_fail_safely_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token'
            for content in ('', 'secret\nsecond-line', 'x' * 16385):
                path.write_text(content)
                with patch.dict(os.environ, {'TEST_TOKEN_FILE': str(path)}), patch('backend.app.collectors.base.cli_token') as cli:
                    with self.assertRaises(CollectionError) as error:
                        local_token('TEST_TOKEN_FILE', ['unused'])
                    self.assertNotIn('secret', str(error.exception))
                    cli.assert_not_called()
            path.unlink()
            with patch.dict(os.environ, {'TEST_TOKEN_FILE': str(path)}), self.assertRaises(CollectionError):
                local_token('TEST_TOKEN_FILE', ['unused'])

    def test_no_mounted_token_uses_local_cli(self):
        with patch.dict(os.environ, {}, clear=True), patch('backend.app.collectors.base.cli_token', return_value='test-only-token') as cli:
            self.assertEqual(local_token('TEST_TOKEN_FILE', ['provider', 'token']), 'test-only-token')
            cli.assert_called_once_with(['provider', 'token'])

    def test_storage_does_not_mark_ambiguous_access_safe(self):
        self.assertIsNone(public_storage({}, {"IsPublic": False}, {"Grants": []}))
        self.assertFalse(public_storage({k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}, None, None))
        self.assertTrue(public_storage({}, {"IsPublic": True}, None))
        self.assertIsNone(public_container({"allowBlobPublicAccess": True}, {}))
        self.assertFalse(public_container({"allowBlobPublicAccess": False}, {"publicAccess": "Container"}))
        self.assertTrue(public_container({"allowBlobPublicAccess": True}, {"publicAccess": "Blob"}))
        self.assertIsNone(public_bucket({}, {"bindings": []}))
        self.assertFalse(public_bucket({"iamConfiguration": {"publicAccessPrevention": "enforced"}}, None))

    def test_port_ranges_and_protocols_are_normalized(self):
        self.assertEqual(rule_ports({"protocol": "Tcp", "destinationPortRange": "20-25"}), [22])
        self.assertEqual(rule_ports({"protocol": "Udp", "destinationPortRange": "22"}), [])
        self.assertEqual(firewall_ports({"allowed": [{"IPProtocol": "tcp", "ports": ["3000-4000"]}]}), [3389])
        self.assertEqual(firewall_ports({"allowed": [{"IPProtocol": "all"}]}), [0])

    def test_redirect_and_pagination_hosts_cannot_receive_credentials(self):
        client = RestClient("secret-token", {"management.azure.com"})
        for url in ("http://management.azure.com/x", "https://evil.example/x", "https://management.azure.com@evil.example/x", "https://management.azure.com:444/x"):
            with self.subTest(url=url), self.assertRaises(CollectionError):
                client.request(url)
        self.assertNotIn("secret-token", repr(client))

    def test_rest_pagination_follows_pages_and_rejects_repeated_tokens(self):
        client = RestClient("token", {"storage.googleapis.com"})
        client.request = Mock(side_effect=[{"items": [1], "nextPageToken": "next"}, {"items": [2]}])
        self.assertEqual(list(client.google_pages("https://storage.googleapis.com/x")), [1, 2])
        client.request = Mock(return_value={"items": [], "nextPageToken": "repeat"})
        with self.assertRaises(CollectionError):
            list(client.google_pages("https://storage.googleapis.com/x"))


class AwsCollectionTest(unittest.TestCase):
    def test_real_sdk_response_contracts_with_stubbed_cloud_calls(self):
        session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="ap-south-1")
        clients = {name: session.client(name) for name in ("sts", "s3", "s3control", "ec2", "iam", "cloudtrail")}
        stubs = {name: Stubber(client) for name, client in clients.items()}
        account = "123456789012"
        stubs["sts"].add_response("get_caller_identity", {"Account": account, "Arn": f"arn:aws:iam::{account}:user/testing", "UserId": "testing"})
        block = {k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}
        stubs["s3control"].add_response("get_public_access_block", {"PublicAccessBlockConfiguration": block}, {"AccountId": account})
        stubs["s3"].add_response("list_buckets", {"Buckets": [{"Name": "test-bucket"}], "ContinuationToken": "more"}, {"MaxBuckets": 100})
        stubs["s3"].add_response("get_bucket_location", {"LocationConstraint": "ap-south-1"}, {"Bucket": "test-bucket"})
        stubs["s3"].add_response("get_public_access_block", {"PublicAccessBlockConfiguration": block}, {"Bucket": "test-bucket"})
        stubs["s3"].add_response("get_bucket_policy_status", {"PolicyStatus": {"IsPublic": False}}, {"Bucket": "test-bucket"})
        stubs["s3"].add_response("get_bucket_acl", {"Grants": []}, {"Bucket": "test-bucket"})
        stubs["s3"].add_response("get_bucket_encryption", {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}}, {"Bucket": "test-bucket"})
        stubs["s3"].add_response("list_buckets", {"Buckets": []}, {"MaxBuckets": 100, "ContinuationToken": "more"})
        stubs["ec2"].add_response("describe_security_groups", {"SecurityGroups": [{"GroupId": "sg-test", "GroupName": "test-ingress", "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 20, "ToPort": 25, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]}]}, {"MaxResults": 100})
        stubs["iam"].add_response("list_users", {"Users": []}, {"MaxItems": 100})
        stubs["cloudtrail"].add_response("describe_trails", {"trailList": []}, {"includeShadowTrails": False})
        raw = {"eventTime": "2026-10-14T10:00:00Z", "eventName": "DeleteResource", "awsRegion": "ap-south-1", "sourceIPAddress": "192.0.2.1", "userIdentity": {"arn": "arn:aws:iam::123456789012:user/test"}}
        stubs["cloudtrail"].add_response("lookup_events", {"Events": [{"EventId": "event-1", "EventName": "DeleteResource", "EventTime": datetime(2026, 10, 14, tzinfo=timezone.utc), "CloudTrailEvent": json.dumps(raw)}]})
        for stub in stubs.values(): stub.activate()
        mock_session = Mock()
        mock_session.client.side_effect = lambda name, **kwargs: clients[name]
        inventory, coverage = collect_aws(CollectionRequest(provider="aws"), mock_session)
        self.assertEqual(len(inventory.resources), 2)
        self.assertFalse(inventory.resources[0].config.public_access)
        self.assertEqual(inventory.resources[1].config.ports, [22])
        self.assertTrue(inventory.events[0].sensitive)
        self.assertTrue(coverage["partial"])
        for stub in stubs.values(): stub.assert_no_pending_responses(); stub.deactivate()

    def test_auth_error_does_not_leak_provider_exception(self):
        session = Mock()
        session.client.return_value.get_caller_identity.side_effect = RuntimeError("SECRET_TOKEN")
        with self.assertRaises(CollectionError) as raised:
            collect_aws(CollectionRequest(provider="aws"), session)
        self.assertNotIn("SECRET_TOKEN", str(raised.exception))


class RestCollectionTest(unittest.TestCase):
    def test_azure_container_and_activity_are_normalized(self):
        rest = Mock()
        def pages(url):
            if "storageAccounts?" in url:
                return iter([{"id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/account", "name": "account", "location": "centralindia", "properties": {"allowBlobPublicAccess": True, "encryption": {"services": {"blob": {"enabled": True}}}}}])
            if "containers?" in url:
                return iter([{"id": "/subscriptions/sub/containers/public", "name": "public", "properties": {"publicAccess": "Blob"}}])
            if "networkSecurityGroups?" in url:
                return iter([])
            return iter([{"eventDataId": "event-1", "eventTimestamp": "2026-10-14T10:00:00Z", "caller": "test-user", "operationName": {"value": "Microsoft.Storage/storageAccounts/delete"}, "status": {"value": "Failed"}, "httpRequest": {"clientIpAddress": "192.0.2.1"}}])
        rest.azure_pages.side_effect = pages
        inventory, metadata = collect_azure(CollectionRequest(provider="azure", account="sub"), rest)
        self.assertTrue(inventory.resources[0].config.public_access)
        self.assertFalse(inventory.events[0].success)
        self.assertTrue(inventory.events[0].sensitive)
        self.assertTrue(metadata["partial"])

    def test_gcp_permission_failure_keeps_unknown_and_reports_partial(self):
        rest = Mock()
        def pages(url, key="items", body=None):
            if "storage/v1/b?" in url:
                return iter([{"name": "bucket", "location": "ASIA-SOUTH1"}])
            if "firewalls" in url:
                return iter([])
            return iter([])
        rest.google_pages.side_effect = pages
        rest.request.side_effect = RuntimeError("SECRET_TOKEN permission denied")
        inventory, metadata = collect_gcp(CollectionRequest(provider="gcp", account="project"), rest)
        self.assertIsNone(inventory.resources[0].config.public_access)
        self.assertTrue(inventory.resources[0].config.encrypted)
        self.assertTrue(metadata["partial"])
        self.assertNotIn("SECRET_TOKEN", json.dumps(metadata))

    def test_no_resources_rejects_snapshot_instead_of_recording_clean_scan(self):
        rest = Mock()
        rest.azure_pages.return_value = iter([])
        with self.assertRaises(CollectionError):
            collect_azure(CollectionRequest(provider="azure", account="sub"), rest)
