frappe.ui.form.on("Annual Leave Disbursement", {
    employee: function (frm) {
        if (!frm.doc.employee) return;
        frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department", "date_of_joining"], (r) => {
            if (r) {
                frm.set_value("employee_name", r.employee_name);
                frm.set_value("company", r.company);
                frm.set_value("department", r.department);
            }
        });
        if (frm.doc.leave_year) {
            frm.trigger("load_leave_balance");
        }
    },

    leave_year: function (frm) {
        if (frm.doc.employee && frm.doc.leave_year) {
            frm.trigger("load_leave_balance");
        }
    },

    load_leave_balance: function (frm) {
        if (!frm.doc.employee || !frm.doc.leave_year) return;
        frappe.call({
            method: "hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement.get_leave_balance",
            args: { employee: frm.doc.employee, leave_year: frm.doc.leave_year },
            callback: function (r) {
                if (r.message) {
                    frm.set_value("leave_days_entitled", r.message.entitled);
                    frm.set_value("leave_days_taken", r.message.taken);
                    frm.set_value("leave_days_balance", r.message.balance);
                    let msg = __("Years of service: {0} → Annual leave entitlement: {1} days (Art.109)",
                        [r.message.years_service, r.message.entitled]);
                    frm.dashboard.add_comment(msg, "blue", true);
                }
            }
        });
    },

    leave_from_date: function (frm) {
        frm.trigger("compute_days");
    },

    leave_to_date: function (frm) {
        frm.trigger("compute_days");
    },

    compute_days: function (frm) {
        if (frm.doc.leave_from_date && frm.doc.leave_to_date) {
            let diff = frappe.datetime.get_diff(frm.doc.leave_to_date, frm.doc.leave_from_date) + 1;
            if (diff > 0) {
                frm.set_value("leave_days_to_pay", diff);
            }
            if (frm.doc.leave_days_balance && diff > frm.doc.leave_days_balance) {
                frappe.msgprint({
                    title: __("Exceeds Balance"),
                    message: __("Leave days ({0}) exceed available balance ({1})", [diff, frm.doc.leave_days_balance]),
                    indicator: "orange"
                });
            }
        }
    },

    monthly_basic_salary: function (frm) {
        if (frm.doc.monthly_basic_salary) {
            frm.set_value("daily_basic_rate", frm.doc.monthly_basic_salary / 30);
        }
        frm.trigger("recalc_pay");
    },

    disbursement_type: function (frm) {
        frm.trigger("recalc_pay");
    },

    leave_days_to_pay: function (frm) {
        frm.trigger("recalc_pay");
    },

    recalc_pay: function (frm) {
        // Client-side preview calc; server-side is authoritative on save
        if (frm.doc.daily_basic_rate && frm.doc.leave_days_to_pay) {
            let basic_pay = frm.doc.daily_basic_rate * frm.doc.leave_days_to_pay;
            frm.set_value("basic_leave_pay", basic_pay);
        }
    },

    refresh: function (frm) {
        frm.set_intro(
            __("Annual Leave Disbursement per Saudi Labor Law Art.109. " +
               "Employee is entitled to full salary during annual leave. " +
               "Payment must be made BEFORE the leave starts."),
            "blue"
        );

        if (frm.doc.docstatus === 1 && frm.doc.status !== "Paid") {
            frm.add_custom_button(__("Mark as Paid"), function () {
                frappe.confirm(
                    __("Confirm leave disbursement payment of SAR {0}?", [format_currency(frm.doc.total_leave_pay)]),
                    function () {
                        frappe.db.set_value("Annual Leave Disbursement", frm.doc.name, "status", "Paid")
                            .then(() => frm.reload_doc());
                    }
                );
            }, __("Actions"));
        }

        // Show entitlement law reference
        if (frm.doc.leave_days_entitled) {
            let basis = frm.doc.leave_days_entitled === 30 ?
                __("30 days (>5 years service - Art.109)") :
                __("21 days (<5 years service - Art.109)");
            frm.dashboard.add_comment(__("Entitlement: ") + basis, "green", true);
        }
    }
});
