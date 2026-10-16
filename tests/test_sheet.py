from datetime import date

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestAttendanceSheet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rule = cls.env['hr.attendance.rule']._get_rule(cls.env.company)
        cls.rule.write({
            'level2_days': 3, 'level3_days': 7, 'late_count_threshold': 3, 'late_cut_days': 1,
            'days_in_month': 30, 'hours_per_day': 8, 'overtime_rate': 2,
        })
        cls.employee = cls.env['hr.employee'].create({'name': "Test Employee"})

    def test_rule_thresholds_are_consistent(self):
        with self.assertRaises(ValidationError):
            self.rule.write({'level2_days': 10, 'level3_days': 5})

    def test_sheet_period(self):
        sheet = self.env['hr.attendance.sheet'].create({'month': '2', 'year': 2026})
        self.assertEqual(sheet.date_from, date(2026, 2, 1))
        self.assertEqual(sheet.date_to, date(2026, 2, 28))
        self.assertEqual(sheet.name, "February 2026")

    def test_line_amounts(self):
        sheet = self.env['hr.attendance.sheet'].create({'month': '3', 'year': 2026})
        line = self.env['hr.attendance.sheet.line'].create({
            'sheet_id': sheet.id,
            'employee_id': self.employee.id,
            'monthly_gross': 30000.0,
            'late_count': 6,        # 2 groups of 3 lates -> 2 days
            'absent_days': 1.0,     # 1 day
            'unpaid_leave_days': 0.0,
            'ot_hours': 8.0,
        })
        # 3 days at 1000/day, overtime at 125/h x 2
        self.assertEqual(line.late_deduction_days, 2.0)
        self.assertEqual(line.total_deduction_days, 3.0)
        self.assertAlmostEqual(line.deduction_amount, 3000.0)
        self.assertAlmostEqual(line.ot_amount, 2000.0)
        self.assertAlmostEqual(line.net_adjustment, -1000.0)
        self.assertAlmostEqual(sheet.total_net_adjustment, -1000.0)

    def test_one_sheet_per_month(self):
        self.env['hr.attendance.sheet'].create({'month': '4', 'year': 2026})
        with self.assertRaises(Exception):
            self.env['hr.attendance.sheet'].create({'month': '4', 'year': 2026})
