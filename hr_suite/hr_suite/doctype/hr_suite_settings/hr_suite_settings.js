const EMPLOYEE_FIELDS = ["name", "employee_name", "user_id", "branch", "department", "company"];

async function clientCall(method, args) {
	const response = await frappe.call(method, args || {});
	return response.message;
}

async function fetchActiveEmployees() {
	return clientCall("frappe.client.get_list", {
		doctype: "Employee",
		fields: EMPLOYEE_FIELDS,
		filters: { status: "Active" },
		order_by: "employee_name asc, name asc",
		limit_page_length: 5000,
	});
}

async function fetchBranches() {
	const branches = await clientCall("frappe.client.get_list", {
		doctype: "Branch",
		fields: ["name"],
		order_by: "name asc",
		limit_page_length: 5000,
	});
	return (branches || []).map((row) => row.name).filter(Boolean);
}

async function syncDirectoryTable(frm, { save = false } = {}) {
	const rows = await fetchActiveEmployees();
	frm.clear_table("branch_employee_directory");
	(rows || []).forEach((row) => {
		frm.add_child("branch_employee_directory", {
			employee: row.name,
			employee_name: row.employee_name,
			user_id: row.user_id,
			branch: row.branch,
			department: row.department,
			company: row.company,
		});
	});
	frm.refresh_field("branch_employee_directory");
	if (save) {
		await frm.save();
	}
	return rows || [];
}

function escapeCell(value) {
	return String(value || "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/\"/g, "&quot;");
}

function buildExcelHtml(employees, branches) {
	const employeeRows = (employees || [])
		.map(
			(row) => `
				<tr>
					<td>${escapeCell(row.name)}</td>
					<td>${escapeCell(row.employee_name)}</td>
					<td>${escapeCell(row.user_id)}</td>
					<td>${escapeCell(row.branch)}</td>
					<td>${escapeCell(row.branch)}</td>
				</tr>`
		)
		.join("");

	const branchRows = (branches || [])
		.map((branch) => `<tr><td>${escapeCell(branch)}</td></tr>`)
		.join("");

	return `<!DOCTYPE html>
		<html>
		<head>
			<meta charset="utf-8">
			<style>
				table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
				th, td { border: 1px solid #cfd8d3; padding: 8px; text-align: left; }
				th { background: #e8f3ee; font-weight: 700; }
				h1 { color: #17684f; }
				p { color: #4d5f57; }
			</style>
		</head>
		<body>
			<h1>Employee Branch Template</h1>
			<p>Update only the target_branch column, then attach this file in Hr Suite Settings and run Import Employee Branches.</p>
			<table data-sheet="Employees">
				<thead>
					<tr>
						<th>employee_id</th>
						<th>employee_name</th>
						<th>user_id</th>
						<th>current_branch</th>
						<th>target_branch</th>
					</tr>
				</thead>
				<tbody>${employeeRows}</tbody>
			</table>
			<table data-sheet="Branches">
				<thead><tr><th>branch_name</th></tr></thead>
				<tbody>${branchRows}</tbody>
			</table>
		</body>
		</html>`;
}

function downloadTemplateFile(content, fileName) {
	const blob = new Blob([content], { type: "application/vnd.ms-excel;charset=utf-8" });
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = fileName;
	link.click();
	URL.revokeObjectURL(url);
}

function parseCsv(text) {
	return text
		.split(/\r?\n/)
		.filter((line) => line.trim())
		.map((line) => line.split(",").map((value) => value.trim().replace(/^"|"$/g, "")));
}

function parseHtmlTemplate(text) {
	const parser = new DOMParser();
	const doc = parser.parseFromString(text, "text/html");
	const table = doc.querySelector('table[data-sheet="Employees"]') || doc.querySelector("table");
	if (!table) {
		throw new Error(__("The attached file does not contain the Employees template table."));
	}

	return Array.from(table.querySelectorAll("tr")).map((row) =>
		Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent.trim())
	);
}

async function parseImportFile(fileUrl) {
	const response = await fetch(fileUrl, { credentials: "same-origin" });
	if (!response.ok) {
		throw new Error(__("Unable to read the attached template file."));
	}

	const lowerUrl = (fileUrl || "").toLowerCase();
	if (lowerUrl.endsWith(".csv")) {
		return parseCsv(await response.text());
	}

	if (lowerUrl.endsWith(".xls") || lowerUrl.endsWith(".html") || lowerUrl.endsWith(".htm")) {
		return parseHtmlTemplate(await response.text());
	}

	throw new Error(__("Use the downloaded template (.xls) or a CSV file for bulk import."));
}

function toPayloadRows(matrix) {
	const [headerRow, ...dataRows] = matrix || [];
	const headers = (headerRow || []).map((value) => String(value || "").trim().toLowerCase());
	return dataRows.map((row) => {
		const payload = {};
		headers.forEach((header, index) => {
			payload[header] = String(row[index] || "").trim();
		});
		return payload;
	});
}

async function ensureBranch(branchName) {
	if (!branchName) {
		return;
	}

	const existing = await clientCall("frappe.client.get_list", {
		doctype: "Branch",
		fields: ["name"],
		filters: { name: branchName },
		limit_page_length: 1,
	});
	if (!existing || !existing.length) {
		await clientCall("frappe.client.insert", { doc: { doctype: "Branch", branch: branchName } });
	}
}

function findEmployeeRecord(employees, row) {
	return (employees || []).find((employee) =>
		employee.name === row.employee_id ||
		(employee.user_id && employee.user_id === row.user_id) ||
		(employee.employee_name && employee.employee_name === row.employee_name)
	);
}

async function importEmployeeBranches(frm) {
	if (!frm.doc.employee_branch_import_file) {
		frappe.msgprint({
			title: __("Excel File Required"),
			message: __("Attach the template file first, then run the import."),
			indicator: "orange",
		});
		return;
	}

	const employees = await fetchActiveEmployees();
	const existingBranches = new Set(await fetchBranches());
	const rows = toPayloadRows(await parseImportFile(frm.doc.employee_branch_import_file));
	let updatedCount = 0;
	let createdBranchCount = 0;
	let skippedCount = 0;
	const errors = [];

	for (const row of rows) {
		const targetBranch = row.target_branch || row.branch || row.current_branch;
		if (!row.employee_id && !row.user_id && !row.employee_name && !targetBranch) {
			continue;
		}
		if (!targetBranch) {
			skippedCount += 1;
			continue;
		}

		const employee = findEmployeeRecord(employees, row);
		if (!employee) {
			errors.push(__("Employee not found: {0}", [row.employee_id || row.user_id || row.employee_name]));
			continue;
		}

		try {
			if (!existingBranches.has(targetBranch)) {
				createdBranchCount += 1;
				existingBranches.add(targetBranch);
			}
			await ensureBranch(targetBranch);
			if (!employee.branch || employee.branch !== targetBranch) {
				await clientCall("frappe.client.set_value", {
					doctype: "Employee",
					name: employee.name,
					fieldname: "branch",
					value: targetBranch,
				});
				employee.branch = targetBranch;
				updatedCount += 1;
			} else {
				skippedCount += 1;
			}
		} catch (error) {
			errors.push(error.message || String(error));
		}
	}

	await syncDirectoryTable(frm, { save: true });
	frappe.msgprint({
		title: __("Import Completed"),
		message: __("Updated: {0}<br>Created Branches: {1}<br>Skipped: {2}", [updatedCount, createdBranchCount, skippedCount])
			+ (errors.length ? `<br><br>${errors.slice(0, 10).join("<br>")}` : ""),
		indicator: errors.length ? "orange" : "green",
	});
}

async function refreshAttendanceApiReference(frm) {
	const result = await clientCall(
		"hr_suite.hr_suite.doctype.hr_suite_settings.hr_suite_settings.refresh_mobile_attendance_api_reference"
	);
	frm.set_value("mobile_attendance_api_reference", result.reference);
	frm.refresh_field("mobile_attendance_api_reference");
	frappe.show_alert({ message: __("Attendance API reference refreshed"), indicator: "green" });
	return result;
}

frappe.ui.form.on("Hr Suite Settings", {
	async refresh(frm) {
		frm.add_custom_button(__("Refresh Employee Branches"), async () => {
			const rows = await syncDirectoryTable(frm, { save: true });
			frappe.show_alert({
				message: __("Employee branch directory refreshed: {0}", [rows.length]),
				indicator: "green",
			});
		});

		frm.add_custom_button(__("Download Excel Template"), async () => {
			const employees = await fetchActiveEmployees();
			const branches = await fetchBranches();
			downloadTemplateFile(buildExcelHtml(employees, branches), "employee-branch-template.xls");
		});

		frm.add_custom_button(__("Import Employee Branches"), async () => {
			await importEmployeeBranches(frm);
		});

		if (frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Refresh External API Reference"), async () => {
				await refreshAttendanceApiReference(frm);
			}, __("External API"));
		}

		if (!frm.doc.branch_employee_directory || !frm.doc.branch_employee_directory.length) {
			await syncDirectoryTable(frm, { save: true });
		}
	},
});