"""PII classification, data sensitivity tags, and masking policy foundation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


def get_policy_tag_path(field_name: str) -> str:
    """Build dynamic policy tag path from Settings configuration."""
    try:
        from pwa.settings import get_settings

        settings = get_settings()
        proj = getattr(settings, "gcp_project", "pwa-prod") or "pwa-prod"
        location = getattr(settings, "gcp_location", "eu") or "eu"
        taxonomy = getattr(settings, "pii_taxonomy_id", "pii_taxonomy") or "pii_taxonomy"
        return f"projects/{proj}/locations/{location}/taxonomies/{taxonomy}/policyTags/{field_name}"
    except Exception:
        return f"projects/pwa-prod/locations/eu/taxonomies/pii_taxonomy/policyTags/{field_name}"


def _policy_tag_project() -> str:
    """Resolve the GCP project for policy-tag resource paths from Settings."""
    try:
        from pwa.settings import get_settings

        return get_settings().gcp_project
    except Exception:
        return "pwa-prod"


class SensitivityLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


@dataclass
class PiiMetadataTag:
    """Metadata tag defining PII classification for a database column."""

    column_name: str
    is_pii: bool
    sensitivity: SensitivityLevel
    policy_tag: Optional[str] = None
    masking_required: bool = False
    owner_team: str = "Data Governance"


# Pre-defined PII metadata registry for common enterprise fields
PII_FIELD_REGISTRY: dict[str, PiiMetadataTag] = {
    "email": PiiMetadataTag(
        "email",
        True,
        SensitivityLevel.RESTRICTED,
        get_policy_tag_path("email"),
        True,
    ),
    "phone": PiiMetadataTag(
        "phone",
        True,
        SensitivityLevel.CONFIDENTIAL,
        get_policy_tag_path("phone"),
        True,
    ),
    "ssn": PiiMetadataTag(
        "ssn",
        True,
        SensitivityLevel.RESTRICTED,
        get_policy_tag_path("ssn"),
        True,
    ),
    "first_name": PiiMetadataTag("first_name", True, SensitivityLevel.CONFIDENTIAL, None, True),
    "last_name": PiiMetadataTag("last_name", True, SensitivityLevel.CONFIDENTIAL, None, True),
    "contact_name": PiiMetadataTag("contact_name", True, SensitivityLevel.CONFIDENTIAL, None, True),
    "address_line1": PiiMetadataTag("address_line1", True, SensitivityLevel.CONFIDENTIAL, None, True),
    "postal_code": PiiMetadataTag("postal_code", True, SensitivityLevel.INTERNAL, None, False),
}


def classify_column(column_name: str) -> PiiMetadataTag:
    """Classify a column based on name heuristics or explicit registry lookup."""
    col_lower = column_name.lower().strip()
    if col_lower in PII_FIELD_REGISTRY:
        return PII_FIELD_REGISTRY[col_lower]

    for key, tag in PII_FIELD_REGISTRY.items():
        if key in col_lower:
            return PiiMetadataTag(
                column_name=column_name,
                is_pii=tag.is_pii,
                sensitivity=tag.sensitivity,
                policy_tag=tag.policy_tag,
                masking_required=tag.masking_required,
            )

    return PiiMetadataTag(
        column_name=column_name, is_pii=False, sensitivity=SensitivityLevel.INTERNAL, masking_required=False
    )


def mask_pii_value(column_name: str, value: Any) -> Any:
    """Mask a single scalar PII value based on column classification rules."""
    if value is None or (isinstance(value, float) and import_math_isnan(value)):
        return value

    val_str = str(value).strip()
    if not val_str:
        return value

    tag = classify_column(column_name)
    if not tag.is_pii or not tag.masking_required:
        return value

    col_lower = column_name.lower()

    if "email" in col_lower:
        if "@" in val_str:
            parts = val_str.split("@", 1)
            user_part = parts[0]
            masked_user = user_part[0] + "***" if len(user_part) > 1 else "***"
            return f"{masked_user}@{parts[1]}"
        return f"{val_str[0]}***@***.com"

    if "phone" in col_lower or "mobile" in col_lower or "fax" in col_lower:
        digits = [c for c in val_str if c.isdigit()]
        if len(digits) >= 4:
            return f"***-***-{''.join(digits[-4:])}"
        return "***-***-****"

    if "ssn" in col_lower:
        return "***-**-****"

    if any(name_key in col_lower for name_key in ["first_name", "last_name", "contact_name", "address"]):
        return f"{val_str[0]}***" if len(val_str) > 1 else "***"

    return "***REDACTED***"


def import_math_isnan(val: float) -> bool:
    import math

    return math.isnan(val)


import os
from typing import Any, Dict, List, Optional


def inspect_content_pii(text: str) -> list[dict[str, Any]]:
    """Perform content-based PII inspection on free-text fields via GCP Cloud DLP API.

    Gated by PWA_DLP_SCAN_ENABLED=1. Scans unstructured text for EMAIL_ADDRESS,
    PHONE_NUMBER, US_SOCIAL_SECURITY_NUMBER, and PERSON_NAME.
    """
    if os.getenv("PWA_DLP_SCAN_ENABLED", "0").strip() != "1" or not text:
        return []

    try:
        from google.cloud import dlp_v2

        client = dlp_v2.DlpServiceClient()
        parent = f"projects/{_policy_tag_project()}"
        item = {"value": str(text)}
        inspect_config = {
            "info_types": [
                {"name": "EMAIL_ADDRESS"},
                {"name": "PHONE_NUMBER"},
                {"name": "US_SOCIAL_SECURITY_NUMBER"},
                {"name": "PERSON_NAME"},
            ],
            "min_likelihood": dlp_v2.Likelihood.LIKELY,
        }
        response = client.inspect_content(
            request={"parent": parent, "inspect_config": inspect_config, "item": item}
        )
        findings = []
        result_obj = getattr(response, "result", response)
        findings_list = getattr(result_obj, "findings", []) or []
        for finding in findings_list:
            info_type_name = getattr(finding.info_type, "name", str(finding.info_type))
            likelihood_name = getattr(finding.likelihood, "name", str(finding.likelihood))
            quote_val = getattr(finding, "quote", "")
            findings.append(
                {
                    "info_type": info_type_name,
                    "likelihood": likelihood_name,
                    "quote": quote_val,
                }
            )
        return findings
    except Exception as exc:
        import logging

        logging.getLogger("pwa.governance.pii").warning(f"[Cloud DLP] Inspection failed ({exc}).")
        return []


def apply_bigquery_column_policy_tags(
    writer: Any,
    dataset_id: str,
    table_name: str,
    columns: list[str],
) -> list[str]:
    """Apply Data Catalog policy tags directly to BigQuery table columns via DDL.

    Emits BigQuery DDL:
    ALTER TABLE `project.dataset.table` ALTER COLUMN col SET OPTIONS (policy_tags=["..."]);

    Returns list of DDL statements executed or prepared.
    """
    ddl_statements = []
    project = getattr(writer, "project", "pwa-prod")

    for col in columns:
        tag = classify_column(col)
        if tag.is_pii and tag.policy_tag:
            ddl = (
                f"ALTER TABLE `{project}.{dataset_id}.{table_name}` "
                f"ALTER COLUMN `{col}` SET OPTIONS (policy_tags=[\"{tag.policy_tag}\"]);"
            )
            ddl_statements.append(ddl)
            if not getattr(writer, "mock", False) and getattr(writer, "_client", None) is not None:
                try:
                    writer._client.query(ddl).result()
                except Exception as exc:
                    import logging

                    logging.getLogger("pwa.governance.pii").warning(
                        f"Could not set policy tag on `{dataset_id}.{table_name}.{col}`: {exc}"
                    )
    return ddl_statements


def mask_dataframe_pii(df: Any, mask_levels: list[SensitivityLevel] | None = None) -> Any:
    """Mask PII columns in a pandas DataFrame post-query execution before returning to UI/exports.

    Modifies or returns a copy of the DataFrame with RESTRICTED/CONFIDENTIAL PII columns masked.
    If PWA_DLP_SCAN_ENABLED=1, also inspects free-text columns for embedded PII.
    """
    import pandas as pd

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    df_masked = df.copy()
    target_levels = mask_levels or [SensitivityLevel.RESTRICTED, SensitivityLevel.CONFIDENTIAL]

    dlp_enabled = os.getenv("PWA_DLP_SCAN_ENABLED", "0").strip() == "1"

    for col in df_masked.columns:
        col_str = str(col)
        tag = classify_column(col_str)

        if tag.is_pii and (tag.masking_required or tag.sensitivity in target_levels):
            df_masked[col] = df_masked[col].apply(lambda v: mask_pii_value(col_str, v))
        elif dlp_enabled and df_masked[col].dtype == object:
            # Free-text column content-based scan
            def _mask_dlp_freetext(val: Any) -> Any:
                if not val or not isinstance(val, str):
                    return val
                findings = inspect_content_pii(val)
                if findings:
                    masked = val
                    for f in findings:
                        q = f.get("quote")
                        if q:
                            masked = masked.replace(q, "***REDACTED_PII***")
                    return masked
                return val

            df_masked[col] = df_masked[col].apply(_mask_dlp_freetext)

    return df_masked

