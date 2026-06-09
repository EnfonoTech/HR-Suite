frappe.ui.form.on("Special Leave", {
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

    leave_type: function (frm) {
        if (!frm.doc.leave_type) return;

        // Set entitled days
        let days = 0;
        if (frm.doc.leave_type.includes("Hajj")) {
            days = 15;
            // Check if Hajj leave has been taken before
            if (frm.doc.employee) {
                frappe.call({
                    method: "hr_suite.hr_suite.doctype.special_leave.special_leave.check_hajj_eligibility",
                    args: { employee: frm.doc.employee },
                    callback: function (r) {
                        if (r.message && !r.message.eligible) {
                            const reasons = [];
                            if (!r.message.minimum_service_met) {
                                reasons.push(
                                    __("Hajj Leave requires at least 2 years of service. Current service: {0} years.", [r.message.years_service || 0])
                                );
                            }
                            if (r.message.prior_count) {
                                reasons.push(
                                    __("This employee has already taken Hajj Leave once during the current employment.")
                                );
                            }
                            frappe.msgprint({
                                title: __("Hajj Leave Not Eligible"),
                                message: reasons.join("<br>"),
                                indicator: "red"
                            });
                        }
                    }
                });
            }
        } else if (frm.doc.leave_type.includes("Bereavement")) {
            days = 5;
        } else if (frm.doc.leave_type.includes("Marriage")) {
            days = 5;
        }
        frm.set_value("entitled_days", days);

        // Auto-set end date based on entitled days
        if (frm.doc.leave_start_date && days > 0) {
            let end = frappe.datetime.add_days(frm.doc.leave_start_date, days - 1);
            frm.set_value("leave_end_date", end);
        }
    },

    leave_start_date: function (frm) {
        if (frm.doc.leave_start_date && frm.doc.entitled_days > 0) {
            let end = frappe.datetime.add_days(frm.doc.leave_start_date, frm.doc.entitled_days - 1);
            frm.set_value("leave_end_date", end);
        }
    },

    leave_end_date: function (frm) {
        if (frm.doc.leave_start_date && frm.doc.leave_end_date) {
            let diff = frappe.datetime.get_diff(frm.doc.leave_end_date, frm.doc.leave_start_date) + 1;
            frm.set_value("actual_days", diff);
            if (frm.doc.entitled_days && diff > frm.doc.entitled_days) {
                frappe.msgprint({
                    title: __("Days Exceeded"),
                    message: __("Actual days ({0}) exceed the entitled days ({1}) per Art.113", [diff, frm.doc.entitled_days]),
                    indicator: "red"
                });
            }
        }
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 1 && !frm.doc.payroll_processed) {
            frm.add_custom_button(__("Mark Payroll Processed"), function () {
                frappe.confirm(
                    __("Mark this special leave payment as processed in payroll?"),
                    function () {
                        frappe.db.set_value("Special Leave", frm.doc.name, "payroll_processed", 1).then(() => {
                            frm.reload_doc();
                        });
                    }
                );
            }, __("Actions"));
        }

        if (frm.doc.is_eligible === 0 && frm.doc.eligibility_notes) {
            frm.dashboard.add_comment(frm.doc.eligibility_notes, "red", true);
        }

        // Law reference
        frm.set_intro(
            __("Special Leaves per Saudi Labor Law Art.113: Hajj (15 days, once per employment after 2 years of service), " +
               "Bereavement (5 days), Marriage (5 days). Paid at full basic salary."),
            "blue"
        );
    }
});
