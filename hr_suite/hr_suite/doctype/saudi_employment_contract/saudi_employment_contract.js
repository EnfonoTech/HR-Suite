// Copyright (c) 2026, Hr Suite and contributors
// Saudi Employment Contract - Client Script

frappe.ui.form.on('Saudi Employment Contract', {

    setup(frm) {
        frm.set_query('employee', function() {
            return { filters: { status: 'Active' } };
        });
    },

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('contract_status', 'Draft');
            frm.set_value('working_hours_per_day', 8);
        }
    },

    employee(frm) {
        if (!frm.doc.employee) return;
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Employee', name: frm.doc.employee },
            callback(r) {
                if (!r.message) return;
                const emp = r.message;
                frm.set_value('employee_name', emp.employee_name);
                frm.set_value('company', emp.company);
                frm.set_value('department', emp.department);
                frm.set_value('designation', emp.designation);
                frm.set_value('nationality', emp.nationality || '');
                frm.set_value('passport_number', emp.passport_number || '');
            }
        });
    },

    start_date(frm) {
        _calc_probation_end(frm);
        _calc_end_date(frm);
    },

    probation_period_days(frm) {
        _calc_probation_end(frm);
    },

    extended_probation_days(frm) {
        _calc_probation_end(frm);
    },

    probation_extended(frm) {
        _calc_probation_end(frm);
    },

    contract_type(frm) {
        _calc_end_date(frm);
    },

    basic_salary(frm)         { _calc_total_salary(frm); },
    housing_allowance(frm)    { _calc_total_salary(frm); },
    transport_allowance(frm)  { _calc_total_salary(frm); },
    other_allowances(frm)     { _calc_total_salary(frm); },
});


function _calc_probation_end(frm) {
    if (!frm.doc.start_date) return;
    let days = cint(frm.doc.probation_period_days) || 90;
    if (frm.doc.probation_extended) {
        days += cint(frm.doc.extended_probation_days) || 0;
    }
    const end = frappe.datetime.add_days(frm.doc.start_date, days);
    frm.set_value('probation_end_date', end);
}

function _calc_end_date(frm) {
    if (frm.doc.contract_type === 'Fixed Term' && frm.doc.start_date) {
        if (!frm.doc.end_date) {
            frm.set_value('end_date', frappe.datetime.add_months(frm.doc.start_date, 12));
        }
    }
}

function _calc_total_salary(frm) {
    const total = flt(frm.doc.basic_salary)
        + flt(frm.doc.housing_allowance)
        + flt(frm.doc.transport_allowance)
        + flt(frm.doc.other_allowances);
    frm.set_value('total_salary', total);
}
