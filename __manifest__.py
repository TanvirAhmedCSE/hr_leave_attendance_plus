{
    'name': 'HR Leave, Attendance & Overtime Plus',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': "Multi-level time off approval, late-arrival rules, overtime pay and monthly "
               "attendance & deduction sheets for Odoo Community.",
    'description': """
HR Leave, Attendance & Overtime Plus
====================================
Extends hr_holidays and hr_attendance with features that Odoo Community does not provide
(Payroll is Enterprise-only):

* Multi-level time off approval: Line Manager -> HR -> Managing Director, chosen by duration
* Late arrival detection (schedule vs first check-in, grace period) on every attendance
* Monthly Attendance & Deduction Sheet (late, absent and unpaid leave deductions, overtime pay)
* Daily cron: reminder for pending approvals; monthly cron: generates last month's sheet
* QWeb PDF report of the sheet
* Portal pages: employees see their own time off and attendance
""",
    'author': 'Tanvir Ahmed',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_holidays', 'hr_attendance', 'portal', 'mail'],
    'data': [
        'security/hr_leave_attendance_plus_security.xml',
        'security/ir.model.access.csv',
        'data/hr_attendance_rule_data.xml',
        'views/hr_attendance_rule_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_attendance_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_sheet_views.xml',
        'report/hr_attendance_sheet_report.xml',
        'views/portal_templates.xml',
        'views/menus.xml',
        'data/ir_cron_data.xml',
    ],
    'application': False,
    'installable': True,
}
