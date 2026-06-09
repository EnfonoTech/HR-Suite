// Copyright (c) 2026, Hr Suite and contributors
// End of Service Benefit - Client Script

frappe.ui.form.on('End of Service Benefit', {

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('termination_date', frappe.datetime.get_today());
            frm.set_value('payment_status', 'Pending');
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
                frm.set_value('joining_date', emp.date_of_joining);
                frm.set_value('nationality', emp.nationality || '');
                frappe.call({
                    method: 'hr_suite.hr_suite.doctype.end_of_service_benefit.end_of_service_benefit.get_last_salary_components',
                    args: { employee: frm.doc.employee },
                    callback(s) {
                        if (s.message) {
                            frm.set_value('last_basic_salary', s.message.basic_salary || 0);
                            frm.set_value('last_total_salary', s.message.total_salary || 0);
                            _trigger_calculation(frm);
                        }
                    }
                });
            }
        });
    },

    joining_date(frm)        { _trigger_calculation(frm); },
    termination_date(frm)    { _trigger_calculation(frm); },
    last_basic_salary(frm)   { _trigger_calculation(frm); },
    last_total_salary(frm)   { _trigger_calculation(frm); },
    eosb_wage_basis(frm)     { _trigger_calculation(frm); },
    termination_reason(frm)  { _trigger_calculation(frm); },
    eosb_deductions(frm)     { _trigger_calculation(frm); },
});


function _trigger_calculation(frm) {
    if (!frm.doc.joining_date || !frm.doc.termination_date || !frm.doc.last_basic_salary) return;

    frappe.call({
        method: 'hr_suite.hr_suite.doctype.end_of_service_benefit.end_of_service_benefit.calculate_eosb_preview',
        args: {
            joining_date: frm.doc.joining_date,
            termination_date: frm.doc.termination_date,
            last_basic_salary: frm.doc.last_basic_salary,
            last_total_salary: frm.doc.last_total_salary || 0,
            eosb_wage_basis: frm.doc.eosb_wage_basis || 'Basic Salary',
            termination_reason: frm.doc.termination_reason || '',
            eosb_deductions: frm.doc.eosb_deductions || 0,
        },
        callback(r) {
            if (!r.message) return;
            const d = r.message;
            frm.set_value('years_of_service',        d.years_of_service);
            frm.set_value('eosb_years_1_5',          d.eosb_years_1_5);
            frm.set_value('eosb_years_above_5',      d.eosb_years_above_5);
            frm.set_value('eosb_gross',              d.eosb_gross);
            frm.set_value('resignation_factor',      d.resignation_factor);
            frm.set_value('resignation_factor_label',d.resignation_factor_label);
            frm.set_value('net_eosb',                d.net_eosb);
            frm.set_value('calculation_notes',       d.calculation_notes);
        }
    });
}
