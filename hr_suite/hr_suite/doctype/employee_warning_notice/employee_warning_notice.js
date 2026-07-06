frappe.ui.form.on("Employee Warning Notice", {
	onload: function (frm) {
		const investigation_field = frm.get_docfield("investigation_record");
		investigation_field.get_route_options_for_new_doc = () => {
			if (!frm.doc.employee) return {};
			return { subject_employee: frm.doc.employee };
		};

		const disciplinary_field = frm.get_docfield("disciplinary_procedure");
		disciplinary_field.get_route_options_for_new_doc = () => {
			if (!frm.doc.employee) return {};
			return { employee: frm.doc.employee };
		};
	},
});
