// Copyright (c) 2026, Hr Suite and contributors
// Termination Notice - Client Script

// Notice periods per Saudi Labor Law
const NOTICE_DAYS = {
    probation: 0,          // During probation: no notice required
    less_than_2: 30,       // Less than 2 years: 30 days
    default: 60,           // 2 years or more: 60 days
};

frappe.ui.form.on('Termination Notice', {

    onload(frm) {
        if (frm.is_new()) {
            frm.set_value('notice_start_date', frappe.datetime.get_today());
            frm.set_value('termination_reason', 'Resignation by Employee');
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

                // Calculate years of service
                if (emp.date_of_joining) {
                    const years = frappe.datetime.get_day_diff(
                        frappe.datetime.get_today(), emp.date_of_joining
                    ) / 365;
                    // Auto-set notice days
                    _set_notice_days(frm, years);
                }

                // Check for active contract
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Country Employment Contract',
                        filters: { employee: frm.doc.employee, contract_status: 'Active' },
                        fields: ['name'],
                        limit: 1
                    },
                    callback(s) {
                        if (s.message && s.message.length) {
                            frm.set_value('eosb_applicable', 1);
                            frm.set_value('eosb_reference', '');
                        }
                    }
                });
            }
        });
    },

    termination_reason(frm) {
        _set_article(frm);
        _calc_notice_end(frm);
    },

    during_probation(frm) {
        if (frm.doc.during_probation) {
            frm.set_value('notice_required_days', 0);
            frm.set_value('eosb_applicable', 0);
            frm.set_value('termination_article', 'Art.77');
            frm.set_value('article_description', 'Termination during probation — No EOSB');
        } else {
            _set_article(frm);
        }
        _calc_notice_end(frm);
    },

    notice_start_date(frm)   { _calc_notice_end(frm); },
    notice_required_days(frm){ _calc_notice_end(frm); },
});


function _set_notice_days(frm, years) {
    if (frm.doc.during_probation) {
        frm.set_value('notice_required_days', 0);
        return;
    }
    if (years < 2) {
        frm.set_value('notice_required_days', NOTICE_DAYS.less_than_2);
    } else {
        frm.set_value('notice_required_days', NOTICE_DAYS.default);
    }
    _calc_notice_end(frm);
}

function _set_article(frm) {
    const reason = frm.doc.termination_reason || '';
    let article = '', description = '';

    if (reason.includes('75') || reason.includes('resignation')) {
        article = 'Art.75';
        description = 'Employee resignation — subject to service period requirements';
        frm.set_value('eosb_applicable', 1);
    } else if (reason.includes('80') || reason.includes('Dismissal') || reason.includes('dismissal')) {
        article = 'Art.80';
        description = 'Disciplinary dismissal — No EOSB';
        frm.set_value('eosb_applicable', 0);
    } else if (reason.includes('74') || reason.includes('Mutual') || reason.includes('Mutual')) {
        article = 'Art.74';
        description = 'Mutual agreement termination';
        frm.set_value('eosb_applicable', 1);
    } else {
        article = 'Art.74';
        description = 'Contract expiry or employer termination — Full EOSB';
        frm.set_value('eosb_applicable', 1);
    }

    frm.set_value('termination_article', article);
    frm.set_value('article_description', description);
}

function _calc_notice_end(frm) {
    if (!frm.doc.notice_start_date) return;
    const days = cint(frm.doc.notice_required_days) || 0;
    const end  = frappe.datetime.add_days(frm.doc.notice_start_date, days);
    frm.set_value('notice_end_date', end);
}
