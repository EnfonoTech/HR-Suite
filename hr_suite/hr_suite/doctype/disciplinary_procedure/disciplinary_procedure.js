frappe.ui.form.on("Disciplinary Procedure", {
    violation_catalog: function (frm) {
        set_catalog_recommendation(frm);
    },

    occurrence_number: function (frm) {
        set_catalog_recommendation(frm);
    },

    employee: function (frm) {
        if (!frm.doc.employee) return;
        frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department"], (r) => {
            if (r) {
                frm.set_value("employee_name", r.employee_name);
                frm.set_value("company", r.company);
                frm.set_value("department", r.department);
            }
        });
        // Load prior warnings
        frappe.call({
            method: "hr_suite.hr_suite.doctype.disciplinary_procedure.disciplinary_procedure.get_prior_warnings",
            args: { employee: frm.doc.employee },
            callback: function (r) {
                if (r.message && r.message.count > 0) {
                    let msg = __("Employee has {0} prior disciplinary record(s).", [r.message.count]);
                    frm.dashboard.add_comment(msg, "yellow", true);
                }
            }
        });
    },

    penalty_type: function (frm) {
        if (!frm.doc.penalty_type) return;
        if (frm.doc.penalty_type.includes("Termination")) {
            frappe.msgprint({
                title: __("Termination for Cause"),
                message: __(
                    "Saudi Labor Law Art.80 requires formal documentation and HRDF notification within 5 days. " +
                    "Please also create a Termination Notice document."
                ),
                indicator: "red"
            });
        }
        // Auto-fill penalty_days for suspension
        if (frm.doc.penalty_type.includes("Suspension") && !frm.doc.penalty_days) {
            frm.set_value("penalty_days", 5); // default max per Art.65
        }
    },

    penalty_days: function (frm) {
        if (frm.doc.penalty_start_date && frm.doc.penalty_days) {
            let end = frappe.datetime.add_days(frm.doc.penalty_start_date, frm.doc.penalty_days - 1);
            frm.set_value("penalty_end_date", end);
        }
    },

    penalty_start_date: function (frm) {
        if (frm.doc.penalty_start_date && frm.doc.penalty_days) {
            let end = frappe.datetime.add_days(frm.doc.penalty_start_date, frm.doc.penalty_days - 1);
            frm.set_value("penalty_end_date", end);
        }
    },

    appeal_submitted: function (frm) {
        if (frm.doc.appeal_submitted) {
            frm.set_value("status", "Appealed");
            frm.set_value("appeal_date", frappe.datetime.get_today());
        }
    },

    refresh: function (frm) {
        // Show prior records count banner
        if (frm.doc.employee && frm.doc.docstatus === 0) {
            frappe.call({
                method: "hr_suite.hr_suite.doctype.disciplinary_procedure.disciplinary_procedure.get_prior_warnings",
                args: { employee: frm.doc.employee },
                callback: function (r) {
                    if (r.message && r.message.count > 0) {
                        let html = `<div style="color:#856404;background:#fff3cd;border:1px solid #ffc107;padding:8px 12px;border-radius:4px;margin-bottom:8px;">
                            <b>⚠ Prior Records:</b> This employee has <b>${r.message.count}</b> prior disciplinary record(s).
                        </div>`;
                        frm.dashboard.add_section(html, __("Disciplinary History"));
                    }
                }
            });
        }

        // Custom button: Create Termination Letter (if penalty = Termination)
        if (frm.doc.docstatus === 1 && frm.doc.penalty_type && frm.doc.penalty_type.includes("Termination")) {
            frm.add_custom_button(__("Create Termination Notice"), function () {
                frappe.new_doc("Termination Notice", {
                    employee: frm.doc.employee,
                    reason_for_termination: "Termination for Cause",
                    reference_doctype: "Disciplinary Procedure",
                    reference_name: frm.doc.name
                });
            }, __("Actions"));
        }

        if (!frm.is_new() && frm.doc.penalty_type) {
            frm.add_custom_button(__("Create Decision Log"), async function () {
                const response = await frappe.call({
                    method: "hr_suite.hr_suite.doctype.disciplinary_procedure.disciplinary_procedure.create_decision_log",
                    args: { doc_name: frm.doc.name }
                });
                await frm.reload_doc();
                if (response.message?.decision_log) {
                    frappe.set_route("Form", "Disciplinary Decision Log", response.message.decision_log);
                }
            }, __("Actions"));
        }

        // Indicate step-by-step status flow
        if (frm.doc.docstatus === 0) {
            let steps = [
                ["1. Record Incident", !!frm.doc.incident_date],
                ["2. Conduct Investigation", !!frm.doc.investigation_date],
                ["3. Get Employee Response", !!frm.doc.employee_response],
                ["4. Issue Penalty", !!frm.doc.penalty_type],
                ["5. HR Manager Approval", !!frm.doc.hr_manager_approval]
            ];
            let completed = steps.filter(s => s[1]).length;
            frm.dashboard.add_progress(__("Procedure Completion"), (completed / steps.length) * 100);
        }
    }
});

function set_catalog_recommendation(frm) {
    if (!frm.doc.violation_catalog) return;
    frappe.db.get_value(
        "Disciplinary Violation Catalog",
        frm.doc.violation_catalog,
        [
            "penalty_first",
            "penalty_second",
            "penalty_third",
            "penalty_fourth",
            "legal_reference",
            "requires_termination_review",
            "status"
        ],
        (r) => {
            if (!r) return;
            const occurrence = Math.min(Math.max(cint(frm.doc.occurrence_number || 1), 1), 4);
            const fieldMap = {
                1: "penalty_first",
                2: "penalty_second",
                3: "penalty_third",
                4: "penalty_fourth"
            };
            frm.set_value("recommended_penalty", r[fieldMap[occurrence]] || "");
            frm.set_value("catalog_legal_reference", r.legal_reference || "");
            frm.set_value(
                "catalog_requires_review",
                r.requires_termination_review || r.status === "Needs Legal Review" ? 1 : 0
            );
        }
    );
}

function cint(value) {
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? 0 : parsed;
}
