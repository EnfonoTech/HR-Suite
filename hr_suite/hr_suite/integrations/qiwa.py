"""
integrations/qiwa.py

Qiwa (Ministry of Human Resources & Social Development — Saudi Arabia) API client.

Operations covered:
  - get_nitaqat_status     : Saudization band for the establishment
  - get_labor_contracts    : list Wathiqa contracts (all or filtered by Iqama)
  - verify_contract        : verify a specific Wathiqa contract
  - get_employee_status    : employee presence and status on Qiwa
  - submit_contract        : create/update a labor contract on Qiwa
  - get_labor_notices      : labor notifications / indharat

Credentials (OAuth2 client credentials) are stored in Hr Suite Settings.
Every request is recorded in Government Portal Sync Log.
"""
import frappe
import requests
from frappe.utils import now_datetime, getdate

_TIMEOUT = 30
_TOKEN_CACHE_KEY = "qiwa_oauth_token"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _settings():
    return frappe.get_single("Hr Suite Settings")


def _get_access_token() -> str:
    """OAuth2 client-credentials token with in-memory cache (per-worker)."""
    cached = frappe.cache().get_value(_TOKEN_CACHE_KEY)
    if cached:
        return cached

    s = _settings()
    if not s.qiwa_enabled:
        frappe.throw("Qiwa integration is not enabled in Hr Suite Settings.")

    base = (s.qiwa_api_base_url or "").rstrip("/")
    resp = requests.post(
        f"{base}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": s.qiwa_client_id,
            "client_secret": s.get_password("qiwa_client_secret"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    token_data = resp.json()
    token = token_data.get("access_token", "")
    expires_in = int(token_data.get("expires_in", 3600)) - 60  # 1 min buffer
    frappe.cache().set_value(_TOKEN_CACHE_KEY, token, expires_in=expires_in)
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base() -> str:
    return (_settings().qiwa_api_base_url or "").rstrip("/")


def _establishment_id() -> str:
    return _settings().qiwa_establishment_id or ""


# ── Core operations ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_nitaqat_status(company: str = None):
    """
    Fetch the current Nitaqat (Saudization) band for the establishment from Qiwa.
    Automatically updates the most recent Nitaqat Record DocType.
    """
    _assert_enabled()
    resp = requests.get(
        f"{_base()}/api/establishments/{_establishment_id()}/nitaqat",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Nitaqat Status", ref=_establishment_id())

    result = {
        "establishment_id": _establishment_id(),
        "saudization_percentage": data.get("saudization_percentage") or data.get("saudizationPercentage"),
        "required_percentage": data.get("required_percentage") or data.get("requiredSaudizationPercentage"),
        "nitaqat_color": data.get("nitaqat_color") or data.get("nitaqatColor") or data.get("band"),
        "nitaqat_category": data.get("nitaqat_category") or data.get("nitaqatCategory"),
        "total_employees": data.get("total_employees") or data.get("totalEmployees"),
        "saudi_employees": data.get("saudi_employees") or data.get("saudiEmployees"),
        "gap_to_next_band": data.get("gap_to_next_band") or data.get("gapToNextBand"),
        "activity_sector": data.get("activity_sector") or data.get("activitySector"),
        "raw": data,
    }

    _log_sync(
        portal="Qiwa",
        sync_type="Nitaqat Status",
        reference_no=_establishment_id(),
        status="Success",
        response_data=frappe.as_json(result),
    )

    _update_nitaqat_record(result, company)
    return result


@frappe.whitelist()
def get_labor_contracts(iqama_number: str = None, employee: str = None):
    """
    List all Wathiqa labor contracts for the establishment,
    optionally filtered by an employee's Iqama number.
    """
    _assert_enabled()
    params = {"establishment_id": _establishment_id()}
    if iqama_number:
        params["iqama_no"] = iqama_number

    resp = requests.get(
        f"{_base()}/api/labor-contracts",
        params=params,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Labor Contracts", ref=iqama_number or _establishment_id())

    contracts = data.get("contracts") or data.get("data") or data if isinstance(data, list) else []

    _log_sync(
        portal="Qiwa",
        sync_type="Labor Contracts",
        employee=employee,
        reference_no=iqama_number or _establishment_id(),
        status="Success",
        response_data=frappe.as_json({"count": len(contracts), "contracts": contracts}),
    )
    return contracts


@frappe.whitelist()
def verify_contract(iqama_number: str, contract_id: str = None, employee: str = None):
    """
    Verify a Wathiqa labor contract. Confirms it is active and matches
    the establishment's records.
    """
    _assert_enabled()
    params = {
        "iqama_no": iqama_number,
        "establishment_id": _establishment_id(),
    }
    if contract_id:
        params["contract_id"] = contract_id

    resp = requests.get(
        f"{_base()}/api/labor-contracts/verify",
        params=params,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Contract Verify", ref=iqama_number)

    result = {
        "iqama_number": iqama_number,
        "contract_id": data.get("contract_id") or contract_id,
        "contract_status": data.get("status") or data.get("contract_status"),
        "start_date": data.get("start_date") or data.get("contractStartDate"),
        "end_date": data.get("end_date") or data.get("contractEndDate"),
        "job_title": data.get("job_title") or data.get("jobTitle"),
        "salary": data.get("salary") or data.get("basicSalary"),
        "is_verified": data.get("is_verified", True),
        "raw": data,
    }

    _log_sync(
        portal="Qiwa",
        sync_type="Contract Verify",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(result),
    )
    return result


@frappe.whitelist()
def get_employee_status(iqama_number: str, employee: str = None):
    """
    Get an employee's current status on the Qiwa platform
    (registered, contract active, violations, etc.).
    """
    _assert_enabled()
    resp = requests.get(
        f"{_base()}/api/employees/{iqama_number}/status",
        params={"establishment_id": _establishment_id()},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Employee Status", ref=iqama_number)

    _log_sync(
        portal="Qiwa",
        sync_type="Employee Status",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    return data


@frappe.whitelist()
def submit_contract(
    iqama_number: str,
    job_title: str,
    basic_salary,
    contract_start: str,
    contract_end: str = None,
    contract_type: str = "Permanent",
    employee: str = None,
):
    """
    Submit or register a new Wathiqa labor contract on Qiwa.
    Typically done when a new employee joins or a contract is renewed.
    """
    _assert_enabled()
    payload = {
        "establishment_id": _establishment_id(),
        "iqama_no": iqama_number,
        "job_title": job_title,
        "basic_salary": float(basic_salary),
        "contract_start_date": contract_start,
        "contract_end_date": contract_end,
        "contract_type": contract_type,
    }
    resp = requests.post(
        f"{_base()}/api/labor-contracts",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Submit Contract", ref=iqama_number)

    _log_sync(
        portal="Qiwa",
        sync_type="Submit Contract",
        employee=employee,
        reference_no=iqama_number,
        status="Success",
        response_data=frappe.as_json(data),
    )
    return data


@frappe.whitelist()
def get_labor_notices(employee: str = None, iqama_number: str = None):
    """Fetch indharat (labor notices / warnings) for an employee or establishment."""
    _assert_enabled()
    params = {"establishment_id": _establishment_id()}
    if iqama_number:
        params["iqama_no"] = iqama_number

    resp = requests.get(
        f"{_base()}/api/labor-notices",
        params=params,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle_response(resp, "Labor Notices", ref=iqama_number or _establishment_id())

    notices = data.get("notices") or data.get("data") or (data if isinstance(data, list) else [])

    _log_sync(
        portal="Qiwa",
        sync_type="Labor Notices",
        employee=employee,
        reference_no=iqama_number or _establishment_id(),
        status="Success",
        response_data=frappe.as_json({"count": len(notices), "notices": notices}),
    )
    return notices


# ── Scheduled sync ────────────────────────────────────────────────────────────

def sync_nitaqat_monthly():
    """Monthly task: refresh Nitaqat band from Qiwa for all SA companies."""
    s = _settings()
    if not s.qiwa_enabled:
        return

    sa_companies = frappe.get_all(
        "Company",
        filters={"country": "Saudi Arabia"},
        fields=["name"],
    )
    for co in sa_companies:
        try:
            get_nitaqat_status(company=co.name)
        except Exception:
            _log_sync(
                portal="Qiwa",
                sync_type="Nitaqat Status",
                reference_no=co.name,
                status="Failed",
                response_data=frappe.get_traceback(),
            )


def sync_employee_contracts(employee: str):
    """
    On-demand: verify all active Saudi employees' Wathiqa contracts with Qiwa.
    Called from Employee form via button.
    """
    s = _settings()
    if not s.qiwa_enabled:
        frappe.throw("Qiwa integration is not enabled.")

    iqama = frappe.db.get_value(
        "Work Permit Iqama",
        {"employee": employee, "iqama_status": ["!=", "Expired"]},
        "iqama_number",
        order_by="iqama_expiry_date desc",
    )
    if not iqama:
        frappe.throw("No active Iqama record found for this employee.")

    return verify_contract(iqama, employee=employee)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _assert_enabled():
    if not _settings().qiwa_enabled:
        frappe.throw("Qiwa integration is not enabled. Configure it in Hr Suite Settings → Qiwa Integration.")


def _handle_response(resp, sync_type: str, ref: str) -> dict:
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
            portal="Qiwa",
            sync_type=sync_type,
            reference_no=ref,
            status="Failed",
            response_data=frappe.as_json({"http_status": resp.status_code, "error": str(e), "body": body}),
        )
        frappe.throw(f"Qiwa API error ({resp.status_code}): {body}")
    except Exception as e:
        _log_sync(
            portal="Qiwa",
            sync_type=sync_type,
            reference_no=ref,
            status="Failed",
            response_data=str(e),
        )
        frappe.throw(f"Qiwa request failed: {e}")


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
        frappe.log_error(frappe.get_traceback(), "HR Suite: Qiwa sync log failed")


def _update_nitaqat_record(result: dict, company: str = None):
    """Create or update a Nitaqat Record with data fetched from Qiwa."""
    from frappe.utils import today
    if not result.get("saudization_percentage"):
        return
    try:
        rec = frappe.get_doc({
            "doctype": "Nitaqat Record",
            "company": company,
            "period_date": today(),
            "saudization_percentage": result.get("saudization_percentage"),
            "required_saudization_percentage": result.get("required_percentage"),
            "nitaqat_color": result.get("nitaqat_color"),
            "nitaqat_category": result.get("nitaqat_category"),
            "total_employees": result.get("total_employees"),
            "saudi_employees": result.get("saudi_employees"),
            "non_saudi_employees": (
                (result.get("total_employees") or 0) - (result.get("saudi_employees") or 0)
            ),
            "gap_to_next_band": result.get("gap_to_next_band"),
            "activity_sector": result.get("activity_sector"),
            "notes": "Auto-synced from Qiwa",
        })
        rec.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: Nitaqat Record update failed")
