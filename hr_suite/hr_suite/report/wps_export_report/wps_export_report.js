frappe.query_reports["WPS Export Report"] = {
    filters: [
        {
            fieldname: "payroll_document",
            label: __("Monthly Payroll"),
            fieldtype: "Link",
            options: "Monthly Payroll",
            // Without a payroll document the report returns nothing at all, which
            // reads as "no employees" rather than "nothing selected".
            reqd: 1
        }
    ],

    onload: function (report) {
        report.page.add_inner_button(__("Download WPS SIF File"), function () {
            let payroll = report.get_filter_value("payroll_document");
            if (!payroll) {
                frappe.msgprint(__("Please select a Monthly Payroll first"));
                return;
            }
            window.location.href = frappe.urllib.get_full_url(
                `/api/method/hr_suite.hr_suite.report.wps_export_report.wps_export_report.download_wps_sif?payroll_document=${encodeURIComponent(payroll)}`
            );
        });
    }
};
