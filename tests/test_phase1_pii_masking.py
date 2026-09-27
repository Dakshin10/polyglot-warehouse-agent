"""Unit tests for Phase 1 PII classification, policy tags, and post-execution masking."""

import pandas as pd
from pwa.governance.pii import (
    SensitivityLevel,
    classify_column,
    get_policy_tag_path,
    mask_dataframe_pii,
    mask_pii_value,
)


def test_pii_policy_tag_path_resolution():
    tag_path = get_policy_tag_path("email")
    assert "policyTags/email" in tag_path
    assert "taxonomies" in tag_path
    assert "123" not in tag_path  # Dummy fake taxonomy 123 replaced


def test_pii_column_classification():
    email_tag = classify_column("email")
    assert email_tag.is_pii is True
    assert email_tag.sensitivity == SensitivityLevel.RESTRICTED
    assert email_tag.masking_required is True

    phone_tag = classify_column("customer_phone")
    assert phone_tag.is_pii is True
    assert phone_tag.sensitivity == SensitivityLevel.CONFIDENTIAL

    amount_tag = classify_column("total_amount")
    assert amount_tag.is_pii is False


def test_mask_pii_value_types():
    assert mask_pii_value("email", "john.doe@company.com") == "j***@company.com"
    assert mask_pii_value("phone", "+1-800-555-0199") == "***-***-0199"
    assert mask_pii_value("ssn", "123-45-6789") == "***-**-****"
    assert mask_pii_value("first_name", "Alice") == "A***"
    assert mask_pii_value("total_amount", 100.50) == 100.50


def test_mask_dataframe_pii_gate():
    df = pd.DataFrame(
        [
            {
                "customer_id": 101,
                "email": "alice@example.com",
                "phone": "+1-555-0123",
                "ssn": "987-65-4321",
                "total_sales": 250.00,
            },
            {
                "customer_id": 102,
                "email": "bob@domain.org",
                "phone": "555-9876",
                "ssn": "111-22-3333",
                "total_sales": 490.50,
            },
        ]
    )

    masked_df = mask_dataframe_pii(df)

    assert masked_df["customer_id"].tolist() == [101, 102]
    assert masked_df["total_sales"].tolist() == [250.00, 490.50]
    assert masked_df["email"].tolist() == ["a***@example.com", "b***@domain.org"]
    assert masked_df["phone"].tolist() == ["***-***-0123", "***-***-9876"]
    assert masked_df["ssn"].tolist() == ["***-**-****", "***-**-****"]
