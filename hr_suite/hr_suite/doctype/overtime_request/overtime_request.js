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
                        }
                        _fetch_overtime_terms(frm);
                    }
                });
            }
        });
    },

    date(frm)        { _fetch_overtime_terms(frm); },
    shift_start(frm) { _calc_overtime_hours(frm); _fetch_overtime_terms(frm); },
    shift_end(frm)   { _calc_overtime_hours(frm); _fetch_overtime_terms(frm); },
    normal_hours(frm){ _calc_overtime_hours(frm); },

    monthly_basic(frm)  { _calc_hourly_rate(frm); },
    overtime_hours(frm) { _calc_amount(frm); },
    overtime_rate(frm)  { _calc_amount(frm); },
    hourly_rate(frm)    { _calc_amount(frm); },
});


function _fetch_overtime_terms(frm) {
    // Rate, day type and the hours-per-month divisor all come from Country Config —
    // Bahrain alone is 1.25x day / 1.5x night+rest+holiday over 240h, not a flat 1.5x
    // over 26x8. Mirrors the server's resolve_overtime_terms() so the preview matches
    // what validate() will actually store.
    if (!frm.doc.employee) return;
    frappe.call({
        method: 'hr_suite.hr_suite.doctype.overtime_request.overtime_request.get_overtime_terms',
        args: {
            employee: frm.doc.employee,
            date: frm.doc.date,
            shift_start: frm.doc.shift_start,
            shift_end: frm.doc.shift_end,
        },
        callback(r) {
            if (!r.message) return;
            frm.set_value('day_type', r.message.day_type);
            frm.set_value('rate_basis', r.message.basis);
            frm.set_value('overtime_rate', r.message.rate);
            frm._overtime_hours_per_month = flt(r.message.hours_per_month);
            _calc_hourly_rate(frm);
        }
    });
}

function _calc_hourly_rate(frm) {
    const basic = flt(frm.doc.monthly_basic);
    const hours_per_month = flt(frm._overtime_hours_per_month);
    if (!basic || !hours_per_month) return;
    const hourly = flt((basic / hours_per_month).toFixed(4));
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
    _calc_amount(frm);
}

function _calc_amount(frm) {
    const hourly   = flt(frm.doc.hourly_rate);
    const ot_hours = flt(frm.doc.overtime_hours);
    const rate     = flt(frm.doc.overtime_rate);
    if (!hourly || !rate) return;
    const amount   = flt((hourly * rate * ot_hours).toFixed(2));
    frm.set_value('overtime_amount', amount);
}
