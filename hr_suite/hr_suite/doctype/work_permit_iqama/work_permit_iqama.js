// Copyright (c) 2026, Enfono Technologies and contributors
// Work Permit Iqama — Client Script
//
// The record is shared by every country HR Suite runs in. `work_country` decides:
//   * what the generic permit fields are CALLED (Country Config.primary_permit_label —
//     "CPR / Work Permit" in Bahrain, "Iqama" in Saudi Arabia), and
//   * whether the Saudi government-portal actions (Muqeem, Qiwa) are offered at all.
// Nothing here hardcodes a country's wording; it is read from Country Config.

frappe.ui.form.on('Work Permit Iqama', {

    refresh(frm) {
        _apply_country_labels(frm);

        if (frm.is_new()) return;

        const is_saudi = (frm.doc.work_country || '') === 'SA';

        frappe.db.get_value("Hr Suite Settings", null, ["muqeem_enabled", "qiwa_enabled"])
            .then(r => {
                const s = r.message || {};

                // Muqeem (MOI) and Qiwa (HRSD) are Saudi portals. Offering "Verify Iqama
                // (Muqeem)" on a Bahrain permit is noise, and the call would fail anyway.
                if (s.muqeem_enabled && is_saudi) {
                    frm.add_custom_button(__("Verify Iqama (Muqeem)"), function () {
                        if (!frm.doc.iqama_number) {
                            frappe.msgprint(__("Enter an Iqama Number first."));
                            return;
                        }
                        frappe.show_progress(__("Contacting Muqeem…"), 0, 100);
                        frappe.call({
                            method: "hr_suite.hr_suite.integrations.muqeem.verify_iqama",
                            args: {
                                iqama_number: frm.doc.iqama_number,
                                employee: frm.doc.employee,
                            },
                            callback(res) {
                                frappe.hide_progress();
                                if (res.exc) return;
                                frappe.show_alert({ message: __("Iqama verified from Muqeem — record updated."), indicator: "green" });
                                frm.reload_doc();
                            },
                        });
                    }, __("Muqeem"));

                    frm.add_custom_button(__("Exit Re-entry Status"), function () {
                        if (!frm.doc.iqama_number) {
                            frappe.msgprint(__("Enter an Iqama Number first."));
                            return;
                        }
                        frappe.call({
                            method: "hr_suite.hr_suite.integrations.muqeem.get_exit_reentry",
                            args: {
                                iqama_number: frm.doc.iqama_number,
                                employee: frm.doc.employee,
                            },
                            callback(res) {
                                if (res.exc) return;
                                const d = res.message || {};
                                frappe.msgprint({
                                    title: __("Exit Re-entry — Muqeem"),
                                    message: `<table class="table table-bordered table-sm" style="font-size:13px;">
                                        <tr><td><b>${__("Visa No.")}</b></td><td>${frappe.utils.escape_html(d.visa_number || "—")}</td></tr>
                                        <tr><td><b>${__("Expiry")}</b></td><td>${frappe.utils.escape_html(d.expiry_date || "—")}</td></tr>
                                        <tr><td><b>${__("Status")}</b></td><td>${frappe.utils.escape_html(d.status || "—")}</td></tr>
                                    </table>`,
                                    indicator: "blue",
                                });
                                frm.reload_doc();
                            },
                        });
                    }, __("Muqeem"));

                    if (frm.doc.employee) {
                        frm.add_custom_button(__("Initiate Final Exit"), function () {
                            frappe.prompt(
                                [{ label: __("Exit Date"), fieldname: "exit_date", fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() }],
                                function(vals) {
                                    frappe.confirm(
                                        __("This will submit a Final Exit request to Muqeem for this employee. Continue?"),
                                        function() {
                                            frappe.call({
                                                method: "hr_suite.hr_suite.integrations.muqeem.initiate_final_exit",
                                                args: {
                                                    iqama_number: frm.doc.iqama_number,
                                                    exit_date: vals.exit_date,
                                                    employee: frm.doc.employee,
                                                },
                                                callback(res) {
                                                    if (res.exc) return;
                                                    frappe.show_alert({ message: __("Final exit request submitted to Muqeem."), indicator: "green" });
                                                },
                                            });
                                        }
                                    );
                                },
                                __("Initiate Final Exit"), __("Submit to Muqeem")
                            );
                        }, __("Muqeem"));
                    }
                }

                if (s.qiwa_enabled && is_saudi && frm.doc.employee) {
                    frm.add_custom_button(__("Verify Wathiqa Contract"), function () {
                        frappe.show_progress(__("Contacting Qiwa…"), 0, 100);
                        frappe.call({
                            method: "hr_suite.hr_suite.integrations.qiwa.verify_contract",
                            args: {
                                iqama_number: frm.doc.iqama_number,
                                employee: frm.doc.employee,
                            },
                            callback(res) {
                                frappe.hide_progress();
                                if (res.exc) return;
                                const d = res.message || {};
                                frappe.msgprint({
                                    title: __("Qiwa — Wathiqa Contract"),
                                    message: `<table class="table table-bordered table-sm" style="font-size:13px;">
                                        <tr><td><b>${__("Contract ID")}</b></td><td>${frappe.utils.escape_html(d.contract_id || "—")}</td></tr>
                                        <tr><td><b>${__("Status")}</b></td><td>${frappe.utils.escape_html(d.contract_status || "—")}</td></tr>
                                        <tr><td><b>${__("Job Title")}</b></td><td>${frappe.utils.escape_html(d.job_title || "—")}</td></tr>
                                        <tr><td><b>${__("Salary")}</b></td><td>${d.salary ? frappe.format(d.salary, {fieldtype:"Currency"}) : "—"}</td></tr>
                                        <tr><td><b>${__("Verified")}</b></td><td>${d.is_verified ? __("Yes") : __("No")}</td></tr>
                                    </table>`,
                                    indicator: d.is_verified ? "green" : "orange",
                                });
                            },
                        });
                    }, __("Qiwa"));
                }

                // Sync log shortcut — Muqeem/Qiwa only write logs for Saudi records.
                if ((s.muqeem_enabled || s.qiwa_enabled) && is_saudi) {
                    frm.add_custom_button(__("View Sync Logs"), function () {
                        frappe.set_route("List", "Government Portal Sync Log", {
                            employee: frm.doc.employee,
                        });
                    });
                }
            });
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
                frm.set_value('nationality', emp.nationality || '');
                frm.set_value('passport_number', emp.passport_number || '');
                // Employee has no `iqama_number` field — the statutory identity number
                // lives on Employee.national_id (CPR in Bahrain, Iqama/National ID in
                // Saudi Arabia). Only pre-fill the Iqama for a Saudi record.
                if (!frm.doc.work_country || frm.doc.work_country === 'SA') {
                    frm.set_value('iqama_number', emp.national_id || '');
                }
                if (!frm.doc.work_country) {
                    frm.set_value('work_country', emp.work_country || '');
                }
            }
        });
    },

    work_country(frm) {
        _apply_country_labels(frm);
        _update_permit_status(frm);
    },

    iqama_expiry_date(frm)       { _update_iqama_status(frm); },
    work_permit_expiry_date(frm) { _update_permit_status(frm); },
});


// Days-before-expiry window for the record's country. Cached per country for the life of
// the page so switching fields does not re-hit the server.
const _country_cache = {};

function _get_country_labels(frm) {
    const country = frm.doc.work_country || '';
    if (_country_cache[country]) return Promise.resolve(_country_cache[country]);
    return frappe.call({
        method: "hr_suite.hr_suite.doctype.work_permit_iqama.work_permit_iqama.get_country_permit_labels",
        args: { work_country: country },
    }).then(r => {
        const labels = (r && r.message) || {};
        _country_cache[country] = labels;
        return labels;
    });
}

function _apply_country_labels(frm) {
    _get_country_labels(frm).then(labels => {
        const permit = labels.permit_label || __("Work Permit");
        frm.set_df_property('work_permit_number', 'label', __("{0} No.", [permit]));
        frm.set_df_property('work_permit_expiry_date', 'label', __("{0} Expiry", [permit]));
        frm.set_df_property('work_permit_issue_date', 'label', __("{0} Issue Date", [permit]));
        frm.set_df_property('work_permit_status', 'label', __("{0} Status", [permit]));
        frm.set_df_property('days_to_permit_expiry', 'label', __("Days to {0} Expiry", [permit]));
        frm.set_df_property('work_permit_section', 'label', permit);
        frm.refresh_field('work_permit_number');
    });
}

function _days_diff(expiry_date) {
    if (!expiry_date) return null;
    return frappe.datetime.get_day_diff(expiry_date, frappe.datetime.get_today());
}

// The Select only accepts Active / Expiring Soon / Expired / N/A. The previous version
// wrote "Expiring", which is not an option, so the value was rejected on save and the
// form and the server disagreed.
function _status_for(days, alert_days) {
    if (days < 0) return 'Expired';
    if (days <= alert_days) return 'Expiring Soon';
    return 'Active';
}

function _update_iqama_status(frm) {
    const days = _days_diff(frm.doc.iqama_expiry_date);
    if (days === null) return;
    frm.set_value('days_to_iqama_expiry', days);
    frm.set_value('iqama_status', _status_for(days, 90));
    _highlight_expiry(frm, 'iqama_expiry_date', days, 90);
}

function _update_permit_status(frm) {
    const days = _days_diff(frm.doc.work_permit_expiry_date);
    if (days === null) return;
    frm.set_value('days_to_permit_expiry', days);
    _get_country_labels(frm).then(labels => {
        const alert_days = labels.alert_days || 90;
        frm.set_value('work_permit_status', _status_for(days, alert_days));
        _highlight_expiry(frm, 'work_permit_expiry_date', days, alert_days);
    });
}

function _highlight_expiry(frm, fieldname, days, alert_days) {
    const $field = frm.get_field(fieldname);
    if (!$field) return;
    $field.$wrapper.removeClass('has-error').css('background-color', '');
    if (days < 0) {
        $field.$wrapper.addClass('has-error');
    } else if (days <= alert_days) {
        $field.$wrapper.css('background-color', '#fff3cd');
    }
}
