"""
salary_override_api.py

Whitelist API for Salary Component Override — history lookup, create override,
and the scheduled task that applies pending future-dated overrides.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime


@frappe.whitelist()
def get_component_history(employee: str, component_name: str, year: str = None):
    """Return override history for one employee + component, newest first."""
    filters = {
        "employee": employee,
        "component_name": component_name,
    }
    records = frappe.get_all(
        "Salary Component Override",
        filters=filters,
        fields=[
            "name", "component_label", "start_date", "end_date",
            "last_value", "new_value", "status", "modified_by_user",
            "applied_on", "creation",
        ],
        order_by="start_date desc, creation desc",
        limit=100,
    )

    if year:
        records = [r for r in records if str(getdate(r.start_date).year) == str(year)]

    return records


@frappe.whitelist()
def save_component_override(
    employee: str,
    component_name: str,
    component_label: str,
    new_value,
    effective_date: str,
    salary_structure_assignment: str = None,
    notes: str = None,
):
    """
    Create a Salary Component Override record.

    - If effective_date <= today: apply immediately to the SSA and mark Applied.
    - If effective_date > today:  mark Pending; scheduler applies it on the due date.
    """
    frappe.has_permission("Salary Component Override", "create", throw=True)

    new_value = flt(new_value)
    effective_date = getdate(effective_date)
    today = getdate()

    # Resolve the SSA if not passed explicitly
    if not salary_structure_assignment:
        salary_structure_assignment = _active_ssa(employee, effective_date)

    # Read the current value before changing it
    last_value = _current_field_value(salary_structure_assignment, component_name)

    status = "Pending" if effective_date > today else "Applied"
    applied_on = now_datetime() if status == "Applied" else None

    # Only retire the previously-active override once this one actually takes effect —
    # a merely-scheduled (Pending) override must not disturb what's currently Applied.
    if status == "Applied":
        _supersede_open_overrides(employee, component_name, effective_date)

    override = frappe.get_doc({
        "doctype": "Salary Component Override",
        "employee": employee,
        "salary_structure_assignment": salary_structure_assignment,
        "component_name": component_name,
        "component_label": component_label or component_name,
        "start_date": effective_date,
        "last_value": last_value,
        "new_value": new_value,
        "status": status,
        "modified_by_user": frappe.session.user,
        "applied_on": applied_on,
        "notes": notes or "",
    })
    override.insert(ignore_permissions=True)

    if status == "Applied":
        _apply_to_ssa(salary_structure_assignment, component_name, new_value)

    frappe.db.commit()
    return {"name": override.name, "status": status}


@frappe.whitelist()
def apply_salary_breakup(
    employee: str,
    salary_structure_assignment: str,
    total_salary,
    effective_date: str,
    notes: str = None,
):
    """
    Look up the country-specific Salary Breakup Table (nearest band at or below
    total_salary) and apply the Basic / HRA / Transport / Other Allowance split
    to the given Salary Structure Assignment, one Salary Component Override per field.

    Country is derived automatically from the employee's active contract / company.
    """
    from hr_suite.hr_suite.doctype.salary_breakup_table.salary_breakup_table import (
        get_breakup_for_total_salary,
    )

    frappe.has_permission("Salary Component Override", "create", throw=True)

    total_salary = flt(total_salary)
    company = frappe.db.get_value("Employee", employee, "company")
    breakup = get_breakup_for_total_salary(total_salary, company)
    if not breakup:
        frappe.throw(
            _(
                "No salary breakup band found for Total Salary {0} for company {1}. "
                "Please import the Salary Breakup Table for {1} first."
            ).format(total_salary, company)
        )

    matched_total = breakup.get("matched_total", total_salary)
    if matched_total != total_salary:
        band_note = _(" (band {0})").format(matched_total)
    else:
        band_note = ""

    default_notes = notes or _(
        "Applied from Salary Breakup Table for Total Salary {0}{1}"
    ).format(total_salary, band_note)

    components = [
        ("custom_total_salary", _("Total Salary"), total_salary),
        ("base", _("Basic"), breakup["basic"]),
        ("custom_hra_amount", _("HRA / Living Allowances"), breakup["hra"]),
        ("custom_transport_amount", _("Transport / Food Allowance"), breakup["transport"]),
        ("custom_other_allowance_amount", _("Other Allowance"), breakup["other_allowance"]),
    ]

    results = []
    for fieldname, label, value in components:
        result = save_component_override(
            employee=employee,
            component_name=fieldname,
            component_label=label,
            new_value=value,
            effective_date=effective_date,
            salary_structure_assignment=salary_structure_assignment,
            notes=default_notes,
        )
        results.append({"component": label, "value": value, **result})

    return {"total_salary": total_salary, "company": company, "breakup": breakup, "results": results}


@frappe.whitelist()
def get_available_years(employee: str, component_name: str):
    """Return distinct years that have history records for the given employee + component."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT YEAR(start_date) AS yr
        FROM `tabSalary Component Override`
        WHERE employee = %s AND component_name = %s
        ORDER BY yr DESC
        """,
        (employee, component_name),
        as_dict=True,
    )
    return [str(r.yr) for r in rows]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _active_ssa(employee: str, as_of_date):
    """Find the most recent Salary Structure Assignment for this employee."""
    ssa = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": employee, "docstatus": 1, "from_date": ["<=", as_of_date]},
        "name",
        order_by="from_date desc",
    )
    return ssa


def _current_field_value(ssa_name: str, component_name: str) -> float:
    if not ssa_name:
        return 0.0
    try:
        val = frappe.db.get_value("Salary Structure Assignment", ssa_name, component_name)
        return flt(val)
    except Exception:
        return 0.0


def _supersede_open_overrides(employee: str, component_name: str, new_start_date, exclude_name: str = None):
    """Mark earlier Pending/Applied overrides for the same component as Superseded,
    and set their end_date to new_start_date - 1 day.

    Only records that take effect on or before new_start_date are affected — a
    later-dated Pending override (still in the future) is left alone."""
    from frappe.utils import add_days

    filters = {
        "employee": employee,
        "component_name": component_name,
        "status": ["in", ["Pending", "Applied"]],
        "start_date": ["<=", new_start_date],
    }
    if exclude_name:
        filters["name"] = ["!=", exclude_name]

    open_records = frappe.get_all(
        "Salary Component Override",
        filters=filters,
        fields=["name", "start_date"],
        order_by="start_date desc",
    )
    for rec in open_records:
        frappe.db.set_value(
            "Salary Component Override",
            rec.name,
            {
                "status": "Superseded",
                "end_date": add_days(new_start_date, -1),
            },
            update_modified=False,
        )


def _apply_to_ssa(ssa_name: str, component_name: str, new_value: float):
    """Write the new value directly into the SSA row (bypasses submit lock)."""
    if not ssa_name:
        return
    if not frappe.db.has_column("Salary Structure Assignment", component_name):
        return
    frappe.db.set_value(
        "Salary Structure Assignment",
        ssa_name,
        component_name,
        new_value,
        update_modified=True,
    )


# ── Scheduled task ────────────────────────────────────────────────────────────

def apply_pending_salary_overrides():
    """Daily task: apply any Pending overrides whose effective date has arrived."""
    today = getdate()
    pending = frappe.get_all(
        "Salary Component Override",
        filters={"status": "Pending", "start_date": ["<=", today]},
        fields=[
            "name", "employee", "salary_structure_assignment",
            "component_name", "new_value",
        ],
    )
    for rec in pending:
        try:
            ssa = rec.salary_structure_assignment or _active_ssa(rec.employee, today)
            _supersede_open_overrides(rec.employee, rec.component_name, rec.start_date, exclude_name=rec.name)
            if ssa:
                _apply_to_ssa(ssa, rec.component_name, flt(rec.new_value))
            frappe.db.set_value(
                "Salary Component Override",
                rec.name,
                {
                    "status": "Applied",
                    "applied_on": now_datetime(),
                    "salary_structure_assignment": ssa,
                },
                update_modified=False,
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"HR Suite: apply_pending_salary_overrides failed for {rec.name}",
            )
    if pending:
        frappe.db.commit()
