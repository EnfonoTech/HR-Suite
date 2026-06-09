frappe.ui.form.on("Medical Examination", {
    employee: function (frm) {
        if (frm.doc.employee) {
            frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department", "designation"], (r) => {
                if (r) {
                    frm.set_value("employee_name", r.employee_name);
                    frm.set_value("company", r.company);
                    frm.set_value("department", r.department);
                    frm.set_value("job", r.designation);
                }
            });
        }
    },

    examination_type: function (frm) {
        // Make work injury reference mandatory for injury-related exams
        let injury_types = ["Post-Injury", "Return to Work"];
        frm.toggle_reqd("work_injury_reference", injury_types.includes(frm.doc.examination_type));
    },

    examination_date: function (frm) {
        if (frm.doc.examination_date) {
            // Auto-fill valid_until = 1 year
            frm.set_value("valid_until", frappe.datetime.add_months(frm.doc.examination_date, 12));
            if (frm.doc.examination_type && frm.doc.examination_type.includes("Periodic")) {
                frm.set_value("next_examination_date", frappe.datetime.add_months(frm.doc.examination_date, 12));
            }
        }
    },

    fitness_result: function (frm) {
        if (!frm.doc.fitness_result) return;
        if (frm.doc.fitness_result.includes("Permanently Unfit")) {
            frappe.msgprint({
                title: __("Alert"),
                message: __("'Permanently Unfit' requires legal HR review under Saudi Labor Law."),
                indicator: "red"
            });
        } else if (frm.doc.fitness_result.includes("Temporarily Unfit")) {
            frappe.msgprint({
                title: __("Alert"),
                message: __("Please set the next examination date."),
                indicator: "orange"
            });
        } else if (frm.doc.fitness_result.includes("Fit with Restrictions")) {
            frappe.msgprint({
                title: __("Alert"),
                message: __("Please document work restrictions in the notes field."),
                indicator: "yellow"
            });
        }
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("View Past Examinations"), function () {
                if (frm.doc.employee) {
                    frappe.set_route("List", "Medical Examination", { employee: frm.doc.employee });
                }
            });
        }
    }
});
