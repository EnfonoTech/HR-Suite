"""
integrations/mudad.py

Mudad / WPS — Wage Protection System (Saudi Arabia)
Ministry of Human Resources integration for salary file compliance:
  · generate_wps_file       — build SIF (Salary Information File) from Salary Slips
  · submit_wps_file         — upload SIF to Mudad portal
  · get_wps_status          — check WPS compliance status for a payroll period
  · get_establishment_status — overall establishment WPS compliance record
  · sync_wps_monthly        — monthly scheduler hook

SIF format follows the SAMA (Saudi Central Bank) Wage Protection specification.
Credentials stored in Hr Suite Settings (mudad_* fields).
Every API call is logged to Government Portal Sync Log (portal = "Mudad").
"""
import frappe
import requests
from frappe.utils import now_datetime, getdate, format_date

_TIMEOUT = 30

# Month-name → zero-padded number map for period conversion
_MONTH_NUM = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _settings():
    return frappe.get_single("Hr Suite Settings")


def _log(sync_type, ref, status, data, employee=None):
    try:
        frappe.get_doc({
            "doctype": "Government Portal Sync Log",
            "portal": "Mudad",
            "sync_type": sync_type,
            "employee": employee,
            "reference_no": ref,
            "status": status,
            "response_data": frappe.as_json(data) if not isinstance(data, str) else data,
            "synced_on": now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: Mudad sync log failed")


def _handle(resp, sync_type, ref, employee=None):
    try:
        resp.raise_for_status()
        data = resp.json()
        _log(sync_type, ref, "Success", data, employee)
        return data
    except requests.HTTPError:
        body = resp.text[:500]
        _log(sync_type, ref, "Failed", {"http": resp.status_code, "body": body}, employee)
        frappe.throw(f"Mudad API error ({resp.status_code}): {body}")
    except Exception as e:
        _log(sync_type, ref, "Failed", str(e), employee)
        frappe.throw(f"Mudad request failed: {e}")


def _headers():
    s = _settings()
    if not s.mudad_enabled:
        frappe.throw("Mudad / WPS integration is not enabled in Hr Suite Settings.")
    return {
        "Authorization": f"Bearer {s.get_password('mudad_api_key')}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Establishment-ID": s.mudad_establishment_id or "",
    }


def _base():
    return (_settings().mudad_api_base_url or "https://api.mudad.com.sa/v1").rstrip("/")


# ── WPS file generation ───────────────────────────────────────────────────────

@frappe.whitelist()
def generate_wps_file(company: str, month: str, year: str):
    """
    Build a WPS Salary Information File (SIF) from submitted Salary Slips.
    Returns the SIF rows as a list — can be previewed before submission.
    """
    s = _settings()
    if not s.mudad_enabled:
        frappe.throw("Mudad / WPS integration is not enabled.")

    start_date = f"{year}-{_MONTH_NUM.get(month, '01')}-01"

    slips = frappe.db.sql("""
        SELECT
            ss.name,
            ss.employee,
            ss.employee_name,
            ss.net_pay,
            ss.gross_pay,
            ss.total_deduction,
            ss.start_date,
            ss.end_date,
            e.bank_ac_no,
            e.bank_name,
            e.iban
        FROM `tabSalary Slip` ss
        INNER JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE ss.company = %(company)s
          AND ss.start_date = %(start_date)s
          AND ss.docstatus = 1
    """, {"company": company, "start_date": start_date}, as_dict=True)

    if not slips:
        frappe.throw(f"No submitted salary slips found for {month} {year} in {company}.")

    establishment_id = s.mudad_establishment_id or ""
    iban = s.mudad_bank_iban or ""

    sif_rows = []
    for slip in slips:
        # SAMA SIF field mapping
        sif_rows.append({
            "employer_iban": iban,
            "employer_bank": s.mudad_bank_code or "",
            "employee_id": slip.employee,
            "employee_name": slip.employee_name,
            "employee_iban": slip.iban or "",
            "employee_bank": slip.bank_name or "",
            "net_salary": float(slip.net_pay or 0),
            "days_worked": 30,
            "salary_start_date": str(slip.start_date or start_date),
            "salary_end_date": str(slip.end_date or ""),
        })

    period_ref = f"{year}-{_MONTH_NUM.get(month, '01')}"
    _log("WPS File Generated", period_ref, "Success", {
        "company": company,
        "month": month,
        "year": year,
        "employee_count": len(sif_rows),
    })

    return {
        "period": period_ref,
        "company": company,
        "establishment_id": establishment_id,
        "employee_count": len(sif_rows),
        "total_net_salary": sum(r["net_salary"] for r in sif_rows),
        "rows": sif_rows,
    }


@frappe.whitelist()
def submit_wps_file(company: str, month: str, year: str):
    """
    Generate and submit the WPS SIF to Mudad for a given payroll period.
    Returns the Mudad reference number and compliance status.
    """
    s = _settings()
    if not s.mudad_enabled:
        frappe.throw("Mudad / WPS integration is not enabled.")

    wps_data = generate_wps_file(company, month, year)

    payload = {
        "establishment_id": s.mudad_establishment_id,
        "payroll_period": wps_data["period"],
        "employer_iban": s.mudad_bank_iban or "",
        "employees": wps_data["rows"],
    }

    resp = requests.post(
        f"{_base()}/wps/submit",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "WPS Submit", wps_data["period"])

    return {
        "period": wps_data["period"],
        "employee_count": wps_data["employee_count"],
        "reference_number": data.get("reference_number") or data.get("referenceNo"),
        "status": data.get("status"),
        "raw": data,
    }


# ── WPS compliance status ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_wps_status(company: str, month: str, year: str):
    """Check WPS compliance status for a specific payroll period on Mudad."""
    s = _settings()
    if not s.mudad_enabled:
        frappe.throw("Mudad / WPS integration is not enabled.")

    period = f"{year}-{_MONTH_NUM.get(month, '01')}"
    resp = requests.get(
        f"{_base()}/wps/status",
        params={
            "establishment_id": s.mudad_establishment_id,
            "period": period,
        },
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "WPS Status", period)
    return {
        "period": period,
        "status": data.get("status") or data.get("wpsStatus"),
        "submitted_on": data.get("submitted_on") or data.get("submittedDate"),
        "employee_count": data.get("employee_count") or data.get("totalEmployees"),
        "total_salary": data.get("total_salary") or data.get("totalAmount"),
        "is_compliant": data.get("is_compliant", True),
        "violation_reason": data.get("violation_reason"),
        "raw": data,
    }


@frappe.whitelist()
def get_establishment_status():
    """Get overall WPS establishment compliance history from Mudad."""
    s = _settings()
    if not s.mudad_enabled:
        frappe.throw("Mudad / WPS integration is not enabled.")

    resp = requests.get(
        f"{_base()}/establishments/{s.mudad_establishment_id}/wps-history",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Establishment Status", s.mudad_establishment_id)
    return {
        "establishment_id": s.mudad_establishment_id,
        "overall_status": data.get("overall_status") or data.get("complianceStatus"),
        "last_submission_period": data.get("last_submission_period"),
        "last_submission_date": data.get("last_submission_date"),
        "pending_periods": data.get("pending_periods", []),
        "raw": data,
    }


# ── Scheduled sync ────────────────────────────────────────────────────────────

def sync_wps_monthly():
    """
    Monthly scheduler: check WPS establishment compliance status.
    Runs via hooks.py scheduler_events (monthly).
    """
    s = _settings()
    if not s.mudad_enabled:
        return
    try:
        get_establishment_status()
    except Exception:
        _log("Establishment Status", s.mudad_establishment_id or "—", "Failed",
             frappe.get_traceback())
