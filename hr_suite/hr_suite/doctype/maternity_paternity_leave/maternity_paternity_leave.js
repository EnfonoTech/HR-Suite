// Copyright (c) 2026, Hr Suite and contributors
// Maternity Paternity Leave - Client Script
// Labor Law Art.151: 10 weeks (70 days) for maternity, Art.160: 3 days for paternity

const LEAVE_ENTITLEMENTS = {
    'Maternity': 70,
    'Paternity': 3,
};

frappe.ui.form.on('Maternity Paternity Leave', {

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('leave_start_date', frappe.datetime.get_today());
            frm.set_value('full_pay', 1);
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
                // Fetch daily salary
                frappe.call({
                    method: 'hr_suite.hr_suite.doctype.maternity_paternity_leave.maternity_paternity_leave.get_daily_salary',
                    args: { employee: frm.doc.employee },
                    callback(s) {
                        if (s.message) {
                            frm.set_value('daily_salary', s.message);
                            _calc_total_pay(frm);
                        }
                    }
                });
            }
        });
    },

    leave_type(frm) {
        const days = LEAVE_ENTITLEMENTS[frm.doc.leave_type];
        if (days !== undefined) {
            frm.set_value('entitled_days', days);
        }
        _set_pay_note(frm);
        _calc_end_date(frm);
    },

    leave_start_date(frm)  { _calc_end_date(frm); },
    entitled_days(frm)     { _calc_end_date(frm); _calc_total_pay(frm); },
    daily_salary(frm)      { _calc_total_pay(frm); },
    full_pay(frm)          { _calc_total_pay(frm); _set_pay_note(frm); },
});


function _calc_end_date(frm) {
    if (!frm.doc.leave_start_date || !frm.doc.entitled_days) return;
    const end = frappe.datetime.add_days(frm.doc.leave_start_date, cint(frm.doc.entitled_days) - 1);
    frm.set_value('leave_end_date', end);
}

function _calc_total_pay(frm) {
    const daily   = flt(frm.doc.daily_salary);
    const days    = cint(frm.doc.entitled_days);
    const rate    = frm.doc.full_pay ? 1.0 : 0.5;
    frm.set_value('total_leave_pay', flt((daily * days * rate).toFixed(2)));
}

function _set_pay_note(frm) {
    const lt = frm.doc.leave_type || '';
    let note = '';
    if (lt.includes('Maternity') || lt.includes('Maternity')) {
        note = 'Maternity leave — 10 weeks full pay per Art.151 Labour Law';
    } else if (lt.includes('Paternity') || lt.includes('Paternity')) {
        note = 'Paternity leave — 3 days full pay per Art.160 Labour Law';
    }
    frm.set_value('pay_note', note);
}
