frappe.ui.form.on("Monthly Attendance Record", {
    employee: function (frm) {
        if (frm.doc.employee) {
            frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department"], (r) => {
                if (r) {
                    frm.set_value("employee_name", r.employee_name);
                    frm.set_value("company", r.company);
                    frm.set_value("department", r.department);
                }
            });
        }
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Auto-Fill Days"), function () {
                if (!frm.doc.month || !frm.doc.year) {
                    frappe.msgprint(__("Please select Month and Year first"));
                    return;
                }
                frappe.call({
                    method: "hr_suite.hr_suite.doctype.monthly_attendance_record.monthly_attendance_record.get_monthly_days",
                    args: { month_label: frm.doc.month, year: frm.doc.year },
                    callback: function (r) {
                        if (r.message && r.message.length) {
                            frm.clear_table("attendance_details");
                            r.message.forEach(row => {
                                let child = frm.add_child("attendance_details");
                                child.attendance_date = row.attendance_date;
                                child.day_of_week = row.day_of_week;
                                child.day_type = row.day_type;
                                child.status = row.status;
                            });
                            frm.refresh_field("attendance_details");
                            frappe.msgprint(__(`Filled ${r.message.length} days`));
                        }
                    }
                });
            }, __("Tools"));
        }
    }
});

frappe.ui.form.on("Monthly Attendance Detail", {
    status: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.status && row.status.includes("Late") && !row.late_minutes) {
            frappe.msgprint(__("Please enter late minutes"));
        }
    },

    time_in: function (frm, cdt, cdn) {
        calculate_hours(frm, cdt, cdn);
    },

    time_out: function (frm, cdt, cdn) {
        calculate_hours(frm, cdt, cdn);
    },

    attendance_details_remove: function (frm) {
        frm.save();
    }
});

function calculate_hours(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (row.time_in && row.time_out) {
        let [h1, m1] = row.time_in.split(":").map(Number);
        let [h2, m2] = row.time_out.split(":").map(Number);
        let mins = (h2 * 60 + m2) - (h1 * 60 + m1);
        if (mins > 0) {
            frappe.model.set_value(cdt, cdn, "hours_worked", parseFloat((mins / 60).toFixed(2)));
            // Standard 8h day → overtime
            let overtime = Math.max(0, (mins / 60) - 8);
            if (overtime > 0) {
                frappe.model.set_value(cdt, cdn, "overtime_hours", parseFloat(overtime.toFixed(2)));
            }
        }
    }
}
