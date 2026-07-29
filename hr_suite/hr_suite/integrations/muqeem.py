"""
integrations/muqeem.py

Muqeem (Ministry of Interior — Saudi Arabia) API client.

Operations covered:
  - verify_iqama          : confirm Iqama validity and expiry
  - get_employee_info     : full expatriate profile from MOI
  - check_visa_status     : exit/re-entry visa status
  - get_exit_reentry      : exit re-entry details
  - initiate_final_exit   : trigger final exit in Muqeem

Credentials are stored in Hr Suite Settings (muqeem_* fields).
Every request is recorded in Government Portal Sync Log.
"""
import frappe
import requests
from frappe.utils import now_datetime, getdate, add_days
from hr_suite.hr_suite.utils import assert_employee_access


_TIMEOUT = 30  # seconds per request


# ── Settings helpers ──────────────────────────────────────────────────────────

def _settings():
    return frappe.get_single("Hr Suite Settings")


def _get_token() -> str:
    """Exchange establishment credentials for a bearer token."""
    s = _settings()
    if not s.muqeem_enabled:
        frappe.throw("Muqeem integration is not enabled in Hr Suite Settings.")

    base = (s.muqeem_api_base_url or "").rstrip("/")
    payload = {
        "establishment_id": s.muqeem_establishment_id,
        "username": s.muqeem_username,
        "password": s.get_password("muqeem_password"),
    }
    resp = requests.post(f"{base}/api/auth/token", json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("token") or data.get("access_token") or ""


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base() -> str:
    return (_settings().muqeem_api_base_url or "").rstrip("/")


# ── Core operations ───────────────────────────────────────────────────────────

@frappe.whitelist()
def verify_iqama(iqama_number: str, employee: str = None):
    """
    Verify an Iqama number against the Muqeem portal.
    Returns live status, profession, expiry date and nationality.
    Saves a sync log and updates the Work Permit Iqama record if one exists.
    """
    assert_employee_access(employee)
    _assert_enabled()
    token = _get_token()
    base = _base()

    resp = requests.get(
        f"{base}/api/iqama/verify",
        params={"iqama_no": iqama_number},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "verify_iqama", iqama_number)

    # Normalise to a predictable shape regardless of API version
    result = {
        "iqama_number": iqama_number,
        "status": data.get("status") or data.get("iqama_status") or "Unknown",
        "expiry_date": data.get("expiry_date") or data.get("iqama_expiry_date"),
        "nationality": data.get("nationality"),
        "profession": data.get("profession") or data.get("job_title"),
        "full_name_en": data.get("full_name_en") or data.get("name_en"),
        "full_name_ar": data.get("full_name_ar") or data.get("name_ar"),
        "sponsor_name": data.get("sponsor_name") or data.get("employer_name"),
        "raw": data,
    }

    _log_sync(
        portal="Muqeem",
        sync_type="Iqama Verify",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(result),
    )

    # Push data back into Work Permit Iqama if record exists
    _update_work_permit_from_muqeem(iqama_number, result)

    return result


@frappe.whitelist()
def get_employee_info(iqama_number: str, employee: str = None):
    """Full expatriate profile from MOI — name, profession, sponsor, visa details."""
    assert_employee_access(employee)
    _assert_enabled()
    token = _get_token()
    resp = requests.get(
        f"{_base()}/api/employee/profile",
        params={"iqama_no": iqama_number},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "get_employee_info", iqama_number)
    _log_sync(
        portal="Muqeem",
        sync_type="Employee Profile",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    return data


@frappe.whitelist()
def check_visa_status(visa_number: str, employee: str = None):
    """Check exit/re-entry or entry visa validity."""
    assert_employee_access(employee)
    _assert_enabled()
    token = _get_token()
    resp = requests.get(
        f"{_base()}/api/visa/status",
        params={"visa_no": visa_number},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "check_visa_status", visa_number)
    _log_sync(
        portal="Muqeem",
        sync_type="Visa Status",
        employee=employee,
        reference_no=visa_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    return data


@frappe.whitelist()
def get_exit_reentry(iqama_number: str, employee: str = None):
    """Retrieve active exit/re-entry visa details from Muqeem."""
    assert_employee_access(employee)
    _assert_enabled()
    token = _get_token()
    resp = requests.get(
        f"{_base()}/api/exit-reentry",
        params={"iqama_no": iqama_number},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "get_exit_reentry", iqama_number)
    _log_sync(
        portal="Muqeem",
        sync_type="Exit Re-entry",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    _update_exit_reentry_fields(iqama_number, data)
    return data


@frappe.whitelist()
def initiate_final_exit(iqama_number: str, exit_date: str, employee: str = None):
    """Trigger a final exit request in Muqeem for an expatriate leaving permanently."""
    assert_employee_access(employee)
    _assert_enabled()
    token = _get_token()
    payload = {
        "iqama_no": iqama_number,
        "exit_date": exit_date,
        "establishment_id": _settings().muqeem_establishment_id,
    }
    resp = requests.post(
        f"{_base()}/api/final-exit",
        json=payload,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "initiate_final_exit", iqama_number)
    _log_sync(
        portal="Muqeem",
        sync_type="Final Exit",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    return data


# ── Scheduled sync ────────────────────────────────────────────────────────────

def sync_expiring_iqamas(days_ahead: int = 90):
    """
    Daily task: verify Iqamas that expire within `days_ahead` days.
    Called from tasks.py.
    """
    s = _settings()
    if not s.muqeem_enabled:
        return

    cutoff = add_days(getdate(), days_ahead)
    records = frappe.get_all(
        "Work Permit Iqama",
        filters={
            "iqama_expiry_date": ["<=", cutoff],
            "iqama_status": ["!=", "Expired"],
        },
        fields=["name", "employee", "iqama_number"],
    )
    for rec in records:
        if not rec.iqama_number:
            continue
        try:
            verify_iqama(rec.iqama_number, employee=rec.employee)
        except Exception:
            _log_sync(
                portal="Muqeem",
                sync_type="Iqama Verify",
                employee=rec.employee,
                reference_no=rec.iqama_number,
                status="Failed",
                response_data=frappe.get_traceback(),
            )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _assert_enabled():
    if not _settings().muqeem_enabled:
        frappe.throw("Muqeem integration is not enabled. Configure it in Hr Suite Settings → Muqeem Integration.")


def _handle_response(resp, operation: str, ref: str) -> dict:
    try:
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        body = ""
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        _log_sync(
            portal="Muqeem",
            sync_type=operation,
            reference_no=ref,
            status="Failed",
            response_data=frappe.as_json({"error": str(e), "body": body}),
        )
        frappe.throw(f"Muqeem API error ({resp.status_code}): {body}")
    except Exception as e:
        _log_sync(
            portal="Muqeem",
            sync_type=operation,
            reference_no=ref,
            status="Failed",
            response_data=str(e),
        )
        frappe.throw(f"Muqeem request failed: {e}")


def _log_sync(portal, sync_type, reference_no, status, response_data, employee=None):
    try:
        frappe.get_doc({
            "doctype": "Government Portal Sync Log",
            "portal": portal,
            "sync_type": sync_type,
            "employee": employee,
            "reference_no": reference_no,
            "status": status,
            "response_data": response_data,
            "synced_on": now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Muqeem sync log failed")


def _update_work_permit_from_muqeem(iqama_number: str, result: dict):
    """Push verified Muqeem data back into the Work Permit Iqama DocType."""
    wp = frappe.db.get_value(
        "Work Permit Iqama",
        {"iqama_number": iqama_number},
        ["name", "iqama_expiry_date", "iqama_status"],
        as_dict=True,
    )
    if not wp:
        return
    updates = {}
    if result.get("expiry_date"):
        updates["iqama_expiry_date"] = result["expiry_date"]
    if result.get("status"):
        updates["iqama_status"] = result["status"]
    if result.get("profession"):
        updates["profession"] = result["profession"]
    if updates:
        frappe.db.set_value("Work Permit Iqama", wp.name, updates, update_modified=True)


def _update_exit_reentry_fields(iqama_number: str, data: dict):
    wp = frappe.db.get_value("Work Permit Iqama", {"iqama_number": iqama_number}, "name")
    if not wp:
        return
    updates = {}
    if data.get("visa_number"):
        updates["exit_reentry_visa_number"] = data["visa_number"]
    if data.get("expiry_date"):
        updates["exit_reentry_expiry_date"] = data["expiry_date"]
    if updates:
        frappe.db.set_value("Work Permit Iqama", wp, updates, update_modified=True)
