// Copyright (c) 2026, Hr Suite and contributors
// Saudi Sick Leave - Client Script
// Saudi Labor Law Art.117: 30 days full pay, 60 days at 75%, 30 days no pay

frappe.ui.form.on('Saudi Sick Leave', {

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('from_date', frappe.datetime.get_today());
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
                // Fetch cumulative sick days this year
                frappe.call({
                    method: 'hr_suite.hr_suite.doctype.saudi_sick_leave.saudi_sick_leave.get_sick_days_this_year',
                    args: { employee: frm.doc.employee, exclude_doc: frm.doc.name || '' },
                    callback(s) {
                        frm.set_value('sick_days_this_year_before', flt(s.message) || 0);
                        _calc_pay(frm);
                    }
                });
                // Fetch daily salary
                frappe.call({
                    method: 'hr_suite.hr_suite.doctype.saudi_sick_leave.saudi_sick_leave.get_daily_salary',
                    args: { employee: frm.doc.employee },
                    callback(s) {
                        if (s.message) frm.set_value('daily_salary', s.message);
                        _calc_pay(frm);
                    }
                });
            }
        });
    },

    from_date(frm) { _calc_days(frm); },
    to_date(frm)   { _calc_days(frm); },

    total_days(frm)                  { _calc_pay(frm); },
    sick_days_this_year_before(frm)  { _calc_pay(frm); },
    daily_salary(frm)                { _calc_pay(frm); },
});


function _calc_days(frm) {
    if (!frm.doc.from_date || !frm.doc.to_date) return;
    if (frm.doc.to_date < frm.doc.from_date) {
        frappe.msgprint(__('To Date cannot be before From Date'));
        frm.set_value('to_date', frm.doc.from_date);
        return;
    }
    const days = frappe.datetime.get_day_diff(frm.doc.to_date, frm.doc.from_date) + 1;
    frm.set_value('total_days', days);
}

function _calc_pay(frm) {
    const before    = flt(frm.doc.sick_days_this_year_before);
    const total     = flt(frm.doc.total_days);
    const after     = before + total;
    const daily     = flt(frm.doc.daily_salary);

    frm.set_value('sick_days_this_year_after', after);

    // Art.117: First bracket (1-30 full pay), second (31-90 at 75%), third (91-120 no pay)
    let pay = 0;
    let rate_label = '';
    let alert_30 = 0, alert_90 = 0;

    if (after <= 30) {
        pay = daily * total;
        rate_label = 'Full Pay (Art.117)';
    } else if (before >= 90) {
        pay = 0;
        rate_label = 'No Pay (Art.117)';
        alert_90 = 1;
    } else {
        // Mixed split
        const full_days = Math.max(0, 30 - before);
        const half_days = Math.max(0, Math.min(60, after - 30) - Math.max(0, before - 30));
        const no_days   = Math.max(0, after - 90);
        pay = daily * full_days + daily * 0.75 * half_days;
        if (full_days && half_days)       rate_label = 'Full + 75% (Art.117)';
        else if (half_days)               rate_label = '75% Pay (Art.117)';
        else if (no_days === total)       { rate_label = 'No Pay (Art.117)'; alert_90 = 1; }
        if (after > 30)  alert_30 = 1;
        if (after >= 90) alert_90 = 1;
    }

    frm.set_value('leave_pay_amount', flt(pay.toFixed(2)));
    frm.set_value('pay_label', rate_label);
    frm.set_value('alert_30_days', alert_30);
    frm.set_value('alert_90_days', alert_90);

    if (alert_90) {
        frappe.show_alert({
            message: __('Warning: Employee exceeded 90 sick days — No pay phase'),
            indicator: 'red'
        });
    } else if (alert_30) {
        frappe.show_alert({
            message: __('Notice: Employee exceeded 30 sick days — 75% pay rate'),
            indicator: 'orange'
        });
    }
}
