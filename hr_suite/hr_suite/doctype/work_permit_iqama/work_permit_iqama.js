// Copyright (c) 2026, Hr Suite and contributors
// Work Permit Iqama - Client Script

frappe.ui.form.on('Work Permit Iqama', {

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
                frm.set_value('nationality', emp.nationality || '');
                frm.set_value('iqama_number', emp.iqama_number || '');
                frm.set_value('passport_number', emp.passport_number || '');
            }
        });
    },

    iqama_expiry_date(frm)       { _update_iqama_status(frm); },
    work_permit_expiry_date(frm) { _update_permit_status(frm); },
});


function _days_diff(expiry_date) {
    if (!expiry_date) return null;
    return frappe.datetime.get_day_diff(expiry_date, frappe.datetime.get_today());
}

function _update_iqama_status(frm) {
    const days = _days_diff(frm.doc.iqama_expiry_date);
    if (days === null) return;
    frm.set_value('days_to_iqama_expiry', days);

    let status;
    if (days < 0)   status = 'Expired';
    else if (days <= 90) status = 'Expiring';
    else            status = 'Active';

    frm.set_value('iqama_status', status);
    _highlight_expiry(frm, 'iqama_expiry_date', days);
}

function _update_permit_status(frm) {
    const days = _days_diff(frm.doc.work_permit_expiry_date);
    if (days === null) return;
    frm.set_value('days_to_permit_expiry', days);

    let status;
    if (days < 0)   status = 'Expired';
    else if (days <= 90) status = 'Expiring';
    else            status = 'Active';

    frm.set_value('work_permit_status', status);
    _highlight_expiry(frm, 'work_permit_expiry_date', days);
}

function _highlight_expiry(frm, fieldname, days) {
    const $field = frm.get_field(fieldname);
    if (!$field) return;
    if (days < 0) {
        $field.$wrapper.addClass('has-error');
    } else if (days <= 90) {
        $field.$wrapper.css('background-color', '#fff3cd');
    }
}
