// Copyright (c) 2026, Hr Suite and contributors
// Overtime Request - Client Script

frappe.ui.form.on('Overtime Request', {

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('date', frappe.datetime.get_today());
            frm.set_value('approval_status', 'Pending');
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
                // Fetch basic salary
                frappe.call({
                    method: 'hr_suite.hr_suite.doctype.overtime_request.overtime_request.get_employee_basic_salary',
                    args: { employee: frm.doc.employee },
                    callback(s) {
                        if (s.message) {
                            frm.set_value('monthly_basic', s.message);
                            _calc_hourly_rate(frm);
                        }
                    }
                });
            }
        });
    },

    monthly_basic(frm) { _calc_hourly_rate(frm); },

    shift_start(frm) { _calc_overtime_hours(frm); },
    shift_end(frm)   { _calc_overtime_hours(frm); },
    normal_hours(frm){ _calc_overtime_hours(frm); },

    overtime_hours(frm) { _calc_amount(frm); },
    overtime_rate(frm)  { _calc_amount(frm); },
    hourly_rate(frm)    { _calc_amount(frm); },
});


function _calc_hourly_rate(frm) {
    const basic = flt(frm.doc.monthly_basic);
    if (!basic) return;
    // Labor Law: Hourly rate = Monthly salary / (26 days x 8 hours)
    const hourly = flt((basic / (26 * 8)).toFixed(4));
    frm.set_value('hourly_rate', hourly);
    _calc_amount(frm);
}

function _calc_overtime_hours(frm) {
    if (!frm.doc.shift_start || !frm.doc.shift_end) return;

    const start = frappe.datetime.str_to_obj(frm.doc.date + ' ' + frm.doc.shift_start);
    let   end   = frappe.datetime.str_to_obj(frm.doc.date + ' ' + frm.doc.shift_end);

    if (!start || !end) return;

    // Handle overnight shifts
    if (end < start) {
        end = new Date(end.getTime() + 24 * 60 * 60 * 1000);
    }

    const total_hours = (end - start) / (1000 * 60 * 60);
    const normal      = flt(frm.doc.normal_hours) || 8;
    const overtime    = Math.max(0, flt((total_hours - normal).toFixed(2)));

    frm.set_value('overtime_hours', overtime);
    // Saudi Labor Law: Overtime rate is 1.5x
    if (!frm.doc.overtime_rate || frm.doc.overtime_rate === 0) {
        frm.set_value('overtime_rate', 1.5);
    }
    _calc_amount(frm);
}

function _calc_amount(frm) {
    const hourly   = flt(frm.doc.hourly_rate);
    const ot_hours = flt(frm.doc.overtime_hours);
    const rate     = flt(frm.doc.overtime_rate) || 1.5;
    const amount   = flt((hourly * rate * ot_hours).toFixed(2));
    frm.set_value('overtime_amount', amount);
}
