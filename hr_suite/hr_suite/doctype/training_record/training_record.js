frappe.ui.form.on("Training Record", {
    employee: function (frm) {
        if (frm.doc.employee) {
            frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department"], (r) => {
                if (r) {
                    frm.set_value("employee_name", r.employee_name);
                    frm.set_value("company", r.company);
                    frm.set_value("department", r.department);
                }
            });
            show_training_summary(frm);
        }
    },

    training_type: function (frm) {
        if (frm.doc.training_type && frm.doc.training_type.includes("Saudization")) {
            frm.set_value("is_saudization_related", 1);
            frm.set_value("is_mandatory", 1);
        }
    },

    training_start_date: function (frm) {
        estimate_hours(frm);
    },

    training_end_date: function (frm) {
        estimate_hours(frm);
    },

    certificate_obtained: function (frm) {
        if (frm.doc.certificate_obtained && frm.doc.training_end_date) {
            // Default certificate expiry to 3 years from training end
            let expiry = frappe.datetime.add_months(frm.doc.training_end_date, 36);
            frm.set_value("certificate_expiry", expiry);
        }
    },

    refresh: function (frm) {
        if (!frm.is_new() && frm.doc.employee) {
            show_training_summary(frm);
        }
    }
});

function estimate_hours(frm) {
    if (frm.doc.training_start_date && frm.doc.training_end_date) {
        let start = frappe.datetime.str_to_obj(frm.doc.training_start_date);
        let end = frappe.datetime.str_to_obj(frm.doc.training_end_date);
        let days = frappe.datetime.get_diff(frm.doc.training_end_date, frm.doc.training_start_date) + 1;
        if (days > 0 && !frm.doc.training_hours) {
            frm.set_value("training_hours", days * 8);
        }
    }
}

function show_training_summary(frm) {
    frappe.call({
        method: "hr_suite.hr_suite.doctype.training_record.training_record.get_employee_training_summary",
        args: { employee: frm.doc.employee },
        callback: function (r) {
            if (r.message && r.message.total_trainings) {
                let d = r.message;
                frm.dashboard.set_headline_alert(
                    `<b>Training Record:</b> ${d.total_trainings} courses | Passed: ${d.passed || 0} | Certificates: ${d.certificates || 0}`
                );
            }
        }
    });
}
