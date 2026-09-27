"""Enterprise Security Posture Unit & Integration Tests.

Executes 100% offline — mocks GCP Secret Manager, GCP Cloud DLP API, and BigQuery clients.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from pwa.governance.pii import (
    SensitivityLevel,
    apply_bigquery_column_policy_tags,
    classify_column,
    inspect_content_pii,
    mask_dataframe_pii,
)
from pwa.settings import (
    EnvSecretProvider,
    GCPSecretManagerProvider,
    Settings,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1: Secrets Management
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecretsManagement:
    def test_env_secret_provider(self):
        provider = EnvSecretProvider()
        with patch.dict(os.environ, {"KAGGLE_KEY": "secret_key_123"}):
            assert provider.get_secret("KAGGLE_KEY") == "secret_key_123"

    def test_gcp_secret_manager_provider_success(self):
        provider = GCPSecretManagerProvider(project_id="test-proj")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = b"secret_from_gcp_123"
        mock_client.access_secret_version.return_value = mock_response

        with patch.object(provider, "_get_client", return_value=mock_client):
            val = provider.get_secret("PG_PASSWORD")
            assert val == "secret_from_gcp_123"
            mock_client.access_secret_version.assert_called_once_with(
                request={"name": "projects/test-proj/secrets/PG_PASSWORD/versions/latest"}
            )

    def test_settings_resolves_secret_provider_based_on_env(self):
        with patch.dict(
            os.environ,
            {
                "GCP_PROJECT": "my-gcp-proj",
                "PWA_ENV": "development",
                "PWA_SECRET_PROVIDER": "env",
                "KAGGLE_USERNAME": "user1",
                "KAGGLE_KEY": "pass1",
            },
        ):
            settings = Settings.from_env()
            assert settings.kaggle_key == "pass1"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 4: Content-Based PII Scanning (Cloud DLP)
# ═══════════════════════════════════════════════════════════════════════════════


class TestContentBasedPiiScanning:
    def test_pii_field_registry_structured_columns(self):
        email_tag = classify_column("email")
        assert email_tag.is_pii is True
        assert email_tag.sensitivity == SensitivityLevel.RESTRICTED

        phone_tag = classify_column("phone")
        assert phone_tag.is_pii is True
        assert phone_tag.sensitivity == SensitivityLevel.CONFIDENTIAL

        unknown_tag = classify_column("ticket_body")
        assert unknown_tag.is_pii is False

    def test_content_scan_disabled_by_default(self):
        with patch.dict(os.environ, {"PWA_DLP_SCAN_ENABLED": "0"}):
            result = inspect_content_pii("Contact me at user@example.com")
            assert result == []

    def test_mocked_dlp_content_scan_flags_embedded_pii_in_freetext(self):
        mock_dlp_client = MagicMock()
        mock_response = MagicMock()

        mock_finding1 = MagicMock()
        mock_finding1.info_type.name = "EMAIL_ADDRESS"
        mock_finding1.likelihood.name = "VERY_LIKELY"
        mock_finding1.quote = "john.doe@company.com"

        mock_finding2 = MagicMock()
        mock_finding2.info_type.name = "US_SOCIAL_SECURITY_NUMBER"
        mock_finding2.likelihood.name = "VERY_LIKELY"
        mock_finding2.quote = "123-45-6789"

        mock_response.result.findings = [mock_finding1, mock_finding2]
        mock_response.findings = [mock_finding1, mock_finding2]
        mock_dlp_client.inspect_content.return_value = mock_response

        mock_dlp_pkg = MagicMock()
        mock_dlp_pkg.DlpServiceClient.return_value = mock_dlp_client

        mock_google = MagicMock()
        mock_google.cloud = MagicMock()
        mock_google.cloud.dlp_v2 = mock_dlp_pkg

        with patch.dict(
            "sys.modules",
            {
                "google": mock_google,
                "google.cloud": mock_google.cloud,
                "google.cloud.dlp_v2": mock_dlp_pkg,
            },
        ):
            with patch.dict(os.environ, {"PWA_DLP_SCAN_ENABLED": "1"}):
                findings = inspect_content_pii(
                    "Support ticket text: user john.doe@company.com reported issue with SSN 123-45-6789"
                )
                assert len(findings) == 2
                assert findings[0]["info_type"] == "EMAIL_ADDRESS"
                assert findings[0]["quote"] == "john.doe@company.com"

    def test_mask_dataframe_pii_with_dlp_freetext(self):
        df = pd.DataFrame(
            [
                {"ticket_messages_body": "Please contact jane.doe@acme.org regarding order 101"},
                {"ticket_messages_body": "No PII present here"},
            ]
        )

        mock_finding = MagicMock()
        mock_finding.info_type.name = "EMAIL_ADDRESS"
        mock_finding.quote = "jane.doe@acme.org"

        mock_response = MagicMock()
        mock_response.result.findings = [mock_finding]
        mock_response.findings = [mock_finding]

        mock_dlp_client = MagicMock()
        mock_dlp_client.inspect_content.return_value = mock_response

        mock_dlp_pkg = MagicMock()
        mock_dlp_pkg.DlpServiceClient.return_value = mock_dlp_client

        mock_google = MagicMock()
        mock_google.cloud = MagicMock()
        mock_google.cloud.dlp_v2 = mock_dlp_pkg

        with patch.dict(
            "sys.modules",
            {
                "google": mock_google,
                "google.cloud": mock_google.cloud,
                "google.cloud.dlp_v2": mock_dlp_pkg,
            },
        ):
            with patch.dict(os.environ, {"PWA_DLP_SCAN_ENABLED": "1"}):
                masked_df = mask_dataframe_pii(df)
                val = masked_df["ticket_messages_body"].iloc[0]
                assert "***REDACTED_PII***" in val
                assert "jane.doe@acme.org" not in val


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5: Warehouse Policy Tag Enforcement
# ═══════════════════════════════════════════════════════════════════════════════


class TestBigQueryPolicyTagEnforcement:
    def test_apply_bigquery_column_policy_tags_generates_ddl(self):
        mock_writer = SimpleNamespace(project="pwa-prod", mock=True, _client=None)
        cols = ["email", "phone", "order_date"]
        ddl_statements = apply_bigquery_column_policy_tags(
            writer=mock_writer, dataset_id="staging_enterprise", table_name="customers", columns=cols
        )

        assert len(ddl_statements) == 2  # email and phone have policy tags
        assert (
            "ALTER TABLE `pwa-prod.staging_enterprise.customers` ALTER COLUMN `email` SET OPTIONS (policy_tags=["
            in ddl_statements[0]
        )
        assert (
            "ALTER TABLE `pwa-prod.staging_enterprise.customers` ALTER COLUMN `phone` SET OPTIONS (policy_tags=["
            in ddl_statements[1]
        )
