frappe.ui.form.on("Saudi Shift Assignment Tool", {
	refresh(frm) {
		frm.disable_save();
		frm.add_custom_button(__("Create Assignments"), () => {
			if (!frm.doc.shift_type || !frm.doc.start_date || !(frm.doc.employees || "").trim()) {
				frappe.msgprint(__("Shift Type, Start Date, and Employees are required."));
				return;
			}

			const employees = (frm.doc.employees || "")
				.split(/\r?\n/)
				.map((row) => row.trim())
				.filter(Boolean);

			frappe.call({
				method: "hr_suite.hr_suite.doctype.saudi_shift_assignment_tool.saudi_shift_assignment_tool.create_assignments",
				args: {
					shift_type: frm.doc.shift_type,
					start_date: frm.doc.start_date,
					end_date: frm.doc.end_date,
					status: frm.doc.status,
					employees,
				},
				freeze: true,
				callback(response) {
					const count = response.message && response.message.count;
					frappe.msgprint(__("{0} Saudi Shift Assignment records created.", [count || 0]));
					frappe.set_route("List", "Saudi Shift Assignment");
				},
			});
		});
	},
});
