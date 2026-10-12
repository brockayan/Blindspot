
"""Vendor inventory validation for Project BlindSpot."""

from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Any

import pandas as pd


@dataclass
class ValidationIssue:
    """One traceable inventory validation issue."""

    severity: str
    code: str
    message: str
    row_number: int | None = None
    vendor_id: str = ""
    column: str = ""


@dataclass
class ValidationReport:
    """Results of validating an inventory table."""

    total_rows: int
    valid_rows: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(
            issue.severity == "Error"
            for issue in self.issues
        )

    @property
    def warning_count(self) -> int:
        return sum(
            issue.severity == "Warning"
            for issue in self.issues
        )

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0


def _is_blank(value: Any) -> bool:
    """Handle empty strings, None, and pandas missing values."""
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    return str(value).strip() == ""


def _normalise_identifier(value: Any) -> str:
    """Normalise an identifier for duplicate detection."""
    if _is_blank(value):
        return ""

    return str(value).strip().casefold()


def duplicate_vendor_ids(inventory: pd.DataFrame) -> list[str]:
    """Return display values for nonblank Vendor IDs that occur more than once."""
    if not isinstance(inventory, pd.DataFrame) or "Vendor ID" not in inventory:
        return []

    occurrences: dict[str, tuple[str, int]] = {}
    for value in inventory["Vendor ID"]:
        if _is_blank(value):
            continue
        normalized = _normalise_identifier(value)
        display, count = occurrences.get(normalized, (str(value).strip(), 0))
        occurrences[normalized] = (display, count + 1)

    return [
        display
        for display, count in occurrences.values()
        if count > 1
    ]


def _valid_public_url(value: Any) -> bool:
    """Check URL syntax without making a network request."""
    if _is_blank(value):
        return True

    value = str(value).strip()

    # A bare domain is accepted by adding HTTPS for syntax checking.
    candidate = value if "://" in value else f"https://{value}"

    try:
        parsed = urlparse(candidate)

        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and "." in parsed.hostname
            and " " not in parsed.hostname
        )
    except ValueError:
        return False


def validate_inventory(
    inventory: pd.DataFrame,
    required_columns: list[str] | None = None,
    url_columns: list[str] | None = None,
) -> ValidationReport:
    """Validate inventory structure and vendor records.

    The function does not modify the original DataFrame.

    Args:
        inventory: Vendor inventory loaded from the workbook.
        required_columns: Columns that must be present and populated.
        url_columns: Columns containing website or URL values.

    Returns:
        A ValidationReport with errors and warnings.
    """
    if not isinstance(inventory, pd.DataFrame):
        raise TypeError("Inventory must be a pandas DataFrame.")

    required_columns = required_columns or [
        "Vendor ID",
        "Vendor Name",
    ]

    url_columns = url_columns or [
        column
        for column in inventory.columns
        if any(
            word in str(column).casefold()
            for word in ("website", "url", "domain")
        )
    ]

    issues: list[ValidationIssue] = []

    # --------------------------------------------------------
    # Schema validation
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in required_columns
        if column not in inventory.columns
    ]

    for column in missing_columns:
        issues.append(
            ValidationIssue(
                severity="Error",
                code="MISSING_COLUMN",
                message=f"Required column '{column}' is missing.",
                column=column,
            )
        )

    if missing_columns:
        return ValidationReport(
            total_rows=len(inventory),
            valid_rows=0,
            issues=issues,
        )

    # --------------------------------------------------------
    # Required fields and duplicate detection
    # --------------------------------------------------------

    id_column = "Vendor ID"
    name_column = "Vendor Name"

    id_occurrences: dict[str, list[int]] = {}
    name_occurrences: dict[str, list[int]] = {}

    for position, (_, row) in enumerate(inventory.iterrows(), start=1):
        vendor_id = row.get(id_column)
        vendor_name = row.get(name_column)

        display_id = (
            ""
            if _is_blank(vendor_id)
            else str(vendor_id).strip()
        )

        if _is_blank(vendor_id):
            issues.append(
                ValidationIssue(
                    severity="Error",
                    code="MISSING_VENDOR_ID",
                    message="Vendor ID is blank.",
                    row_number=position,
                    vendor_id=display_id,
                    column=id_column,
                )
            )
        else:
            normalised_id = _normalise_identifier(vendor_id)
            id_occurrences.setdefault(normalised_id, []).append(position)

        if _is_blank(vendor_name):
            issues.append(
                ValidationIssue(
                    severity="Error",
                    code="MISSING_VENDOR_NAME",
                    message="Vendor Name is blank.",
                    row_number=position,
                    vendor_id=display_id,
                    column=name_column,
                )
            )
        else:
            normalised_name = _normalise_identifier(vendor_name)
            name_occurrences.setdefault(normalised_name, []).append(position)

        for column in required_columns:
            if column not in {id_column, name_column}:
                if _is_blank(row.get(column)):
                    issues.append(
                        ValidationIssue(
                            severity="Warning",
                            code="MISSING_REQUIRED_VALUE",
                            message=f"Required field '{column}' is blank.",
                            row_number=position,
                            vendor_id=display_id,
                            column=column,
                        )
                    )

    for identifier, positions in id_occurrences.items():
        if len(positions) > 1:
            for position in positions:
                issues.append(
                    ValidationIssue(
                        severity="Error",
                        code="DUPLICATE_VENDOR_ID",
                        message=(
                            f"Vendor ID '{identifier}' occurs in "
                            f"inventory rows {positions}."
                        ),
                        row_number=position,
                        vendor_id=identifier,
                        column=id_column,
                    )
                )

    for name, positions in name_occurrences.items():
        if len(positions) > 1:
            for position in positions:
                issues.append(
                    ValidationIssue(
                        severity="Warning",
                        code="DUPLICATE_VENDOR_NAME",
                        message=(
                            f"Vendor name '{name}' occurs in "
                            f"inventory rows {positions}. Confirm whether "
                            "these records represent the same vendor."
                        ),
                        row_number=position,
                        column=name_column,
                    )
                )

    # --------------------------------------------------------
    # URL syntax checks
    # --------------------------------------------------------

    for column in url_columns:
        if column not in inventory.columns:
            issues.append(
                ValidationIssue(
                    severity="Warning",
                    code="URL_COLUMN_NOT_FOUND",
                    message=f"Configured URL column '{column}' was not found.",
                    column=column,
                )
            )
            continue

        for position, (_, row) in enumerate(inventory.iterrows(), start=1):
            value = row.get(column)

            if _is_blank(value):
                continue

            if not _valid_public_url(value):
                issues.append(
                    ValidationIssue(
                        severity="Warning",
                        code="INVALID_URL_FORMAT",
                        message=(
                            f"The value in '{column}' does not appear "
                            "to be a valid HTTP(S) URL or domain."
                        ),
                        row_number=position,
                        vendor_id=str(row.get(id_column, "")),
                        column=column,
                    )
                )

    # Count rows without row-level errors.
    error_rows = {
        issue.row_number
        for issue in issues
        if issue.severity == "Error"
        and issue.row_number is not None
    }

    valid_rows = max(0, len(inventory) - len(error_rows))

    return ValidationReport(
        total_rows=len(inventory),
        valid_rows=valid_rows,
        issues=issues,
    )


def validation_issues_as_records(
    report: ValidationReport,
) -> list[dict[str, Any]]:
    """Convert validation issues to table/export records."""
    return [
        {
            "Severity": issue.severity,
            "Code": issue.code,
            "Message": issue.message,
            "Inventory Row": issue.row_number,
            "Vendor ID": issue.vendor_id,
            "Column": issue.column,
        }
        for issue in report.issues
    ]
