frappe.ui.form.on("Labor Dispute", {
    employee: function (frm) {
        if (!frm.doc.employee) return;
        frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department"], (r) => {
            if (r) {
                frm.set_value("employee_name", r.employee_name);
                frm.set_value("company", r.company);
                frm.set_value("department", r.department);
            }
        });
    },

    dispute_type: function (frm) {
        if (frm.doc.dispute_type && frm.doc.dispute_type.includes("Termination")) {
            frappe.msgprint({
                title: __("Unlawful Termination Claim"),
                message: __(
                    "For unlawful termination claims, the employee may be entitled to up to " +
                    "2 years compensation per Saudi Labor Law Art.77. " +
                    "Ensure full EOSB is documented."
                ),
                indicator: "orange"
            });
        }
    },

    mlsd_submission_date: function (frm) {
        if (frm.doc.mlsd_submission_date && !frm.doc.status.includes("MLSD")) {
            frm.set_value("status", "Referred to MLSD");
        }
    },

    court_case_number: function (frm) {
        if (frm.doc.court_case_number) {
            frm.set_value("status", "Labour Court");
        }
    },

    refresh: function (frm) {
        // Status color indicators
        const statusColors = {
            "Open": "red",
            "Internal Mediation": "orange",
            "Referred to MLSD": "orange",
            "MLSD Mediation": "orange",
            "Labour Court": "red",
            "Resolved": "green",
            "Closed": "grey"
        };
        const color = statusColors[frm.doc.status] || "blue";

        frm.set_intro(
            __("Saudi Labor Law Art.218-221: Disputes must first go through MLSD mediation before the Labour Court. " +
               "MLSD must respond within 10 days."),
            "blue"
        );

        // Days since dispute filed
        if (frm.doc.dispute_date) {
            let days = frappe.datetime.get_diff(frappe.datetime.get_today(), frm.doc.dispute_date);
            if (days > 30 && !frm.doc.status.includes("Resolved") && !frm.doc.status.includes("Closed")) {
                frm.dashboard.add_comment(
                    __("Dispute open for {0} days. Consider escalating to MLSD.", [days]),
                    "orange", true
                );
            }
        }

        // Mark Resolved button
        if (frm.doc.docstatus === 1 && !frm.doc.status.includes("Resolved") && !frm.doc.status.includes("Closed")) {
            frm.add_custom_button(__("Mark Resolved"), function () {
                frappe.prompt([
                    {
                        fieldname: "resolution_notes",
                        label: __("Resolution Notes"),
                        fieldtype: "Text",
                        reqd: 1
                    },
                    {
                        fieldname: "settlement_amount",
                        label: __("Settlement Amount (SAR)"),
                        fieldtype: "Currency"
                    }
                ], function (values) {
                    frappe.db.set_value("Labor Dispute", frm.doc.name, {
                        "status": "Resolved",
                        "internal_resolution": values.resolution_notes,
                        "resolution_amount": values.settlement_amount || 0,
                        "resolution_date": frappe.datetime.get_today()
                    }).then(() => frm.reload_doc());
                }, __("Resolve Dispute"), __("Confirm"));
            }, __("Actions"));
        }
    }
});
