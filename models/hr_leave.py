from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Approval levels, in order. The required number of levels depends on the duration.
STAGES = [
    ('manager', "Line Manager"),
    ('hr', "HR"),
    ('md', "Managing Director"),
]

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    required_level = fields.Selection(
        [('1', "Line Manager"), ('2', "Line Manager + HR"), ('3', "Line Manager + HR + MD")],
        string="Required Approvals", compute='_compute_required_level',
        help="Approval levels required, depending on the duration of the time off.",
    )
    approval_stage = fields.Selection(
        STAGES, string="Waiting For", compute='_compute_approval_stage',
        help="The next approval level the request is waiting for.",
    )
    can_chain_approve = fields.Boolean(compute='_compute_can_chain_approve')

    manager_approver_id = fields.Many2one(
        'res.users', string="Line Manager Approval", copy=False, readonly=True, tracking=True)
    manager_approval_date = fields.Datetime(copy=False, readonly=True)
    hr_approver_id = fields.Many2one(
        'res.users', string="HR Approval", copy=False, readonly=True, tracking=True)
    hr_approval_date = fields.Datetime(copy=False, readonly=True)
    md_approver_id = fields.Many2one(
        'res.users', string="MD Approval", copy=False, readonly=True, tracking=True)
    md_approval_date = fields.Datetime(copy=False, readonly=True)

    #  COMPUTE METHODS  #

    @api.depends('number_of_days', 'employee_id')
    def _compute_required_level(self):
        rule_model = self.env['hr.attendance.rule']
        for leave in self:
            rule = rule_model._get_rule(leave.employee_id.company_id or self.env.company)
            days = leave.number_of_days or 0.0
            if days > rule.level3_days:
                leave.required_level = '3'
            elif days > rule.level2_days:
                leave.required_level = '2'
            else:
                leave.required_level = '1'

    @api.depends(
        'state', 'required_level', 'manager_approver_id', 'hr_approver_id', 'md_approver_id'
    )
    def _compute_approval_stage(self):
        for leave in self:
            stage = False
            if leave.state in ('confirm', 'validate1'):
                for required_stage in leave._get_required_stages():
                    if not leave[f'{required_stage}_approver_id']:
                        stage = required_stage
                        break
            leave.approval_stage = stage

    @api.depends_context('uid')
    @api.depends('approval_stage', 'employee_id')
    def _compute_can_chain_approve(self):
        user = self.env.user
        for leave in self:
            leave.can_chain_approve = bool(leave.approval_stage) and \
                leave._user_can_approve_stage(leave.approval_stage, user)

    #  HELPERS  #

    def _get_required_stages(self):
        self.ensure_one()
        level = int(self.required_level or '1')
        return [stage for stage, _label in STAGES][:level]

    def _user_can_approve_stage(self, stage, user):
        """ Whether the user may approve the given level of this time off. """
        self.ensure_one()
        if self.employee_id.user_id == user:
            return False  # Nobody approves his own time off.

        rule = self.env['hr.attendance.rule']._get_rule(
            self.employee_id.company_id or self.env.company
        )
        if rule.enforce_distinct_approvers:
            previous = self.manager_approver_id | self.hr_approver_id | self.md_approver_id
            if user in previous:
                return False

        is_officer = user.has_group('hr_holidays.group_hr_holidays_user')
        if stage == 'manager':
            return self.employee_id.leave_manager_id == user or is_officer
        if stage == 'hr':
            return is_officer
        if stage == 'md':
            return user.has_group('hr_leave_attendance_plus.group_leave_md')
        return False

    def _get_stage_approver_users(self, stage):
        """ Users who can act on the given level (used for to-do activities). """
        self.ensure_one()
        env_users = self.env['res.users'].sudo()
        group_xmlid = {
            'hr': 'hr_holidays.group_hr_holidays_user',
            'md': 'hr_leave_attendance_plus.group_leave_md',
        }.get(stage)
        if stage == 'manager' and self.employee_id.leave_manager_id:
            users = self.employee_id.leave_manager_id
        else:
            xmlid = group_xmlid or 'hr_holidays.group_hr_holidays_user'
            users = env_users.search([('group_ids', 'in', self.env.ref(xmlid).ids)])
        return users - self.employee_id.user_id

    def _notify_current_stage(self, summary=None):
        """ Schedule a to-do for the approvers of the current level (no duplicates). """
        for leave in self:
            stage = leave.approval_stage
            if not stage:
                continue
            text = summary or _("Approve time off (%s)", dict(STAGES)[stage])
            for user in leave._get_stage_approver_users(stage):
                already = leave.activity_ids.filtered(
                    lambda a, u=user, s=text: a.user_id == u and a.summary == s
                )
                if not already:
                    leave.sudo().activity_schedule(
                        'mail.mail_activity_data_todo', user_id=user.id, summary=text,
                    )

    #  APPROVAL CHAIN  #

    def action_approve(self, check_state=True):
        """ Override: every interactive approval goes through the Manager -> HR -> MD chain.

        Automatic approvals (`check_state=False`, or leave types without validation) keep the
        standard behavior.
        """
        if not check_state or self.env.context.get('hlap_skip_chain'):
            return super().action_approve(check_state=check_state)
        automatic = self.filtered(lambda l: l.validation_type == 'no_validation')
        if automatic:
            super(HrLeave, automatic).action_approve(check_state=check_state)
        for leave in self - automatic:
            leave._chain_approve()
        return True

    def _chain_approve(self):
        self.ensure_one()
        user = self.env.user
        stage = self.approval_stage
        if not stage:
            raise UserError(_("This time off has no pending approval."))
        if not self._user_can_approve_stage(stage, user):
            raise AccessError(_(
                "You are not allowed to approve this time off at the %s level.",
                dict(STAGES)[stage],
            ))

        self.sudo().write({
            f'{stage}_approver_id': user.id,
            f'{stage}_approval_date': fields.Datetime.now(),
        })
        self.sudo().activity_feedback(['mail.mail_activity_data_todo'], user_id=user.id)
        self.sudo().message_post(body=_(
            "%(level)s approval given by %(user)s.", level=dict(STAGES)[stage], user=user.name,
        ))

        if self.approval_stage:
            self._notify_current_stage()
        else:
            # Last level reached: use the standard validation (resource leaves, allocations...).
            self.sudo().with_context(hlap_chain_final=True)._action_validate(check_state=False)

    def action_chain_refuse(self):
        """ Refuse by an approver of the current level who cannot use the standard button. """
        for leave in self:
            stage = leave.approval_stage
            if not stage or not leave._user_can_approve_stage(stage, self.env.user):
                raise AccessError(_("You are not allowed to refuse this time off."))
        return self.sudo().with_context(hlap_chain_final=True).action_refuse()

    def _check_double_validation_rules(self, employees, state):
        if self.env.context.get('hlap_chain_final'):
            return None  # Rights already checked by the approval chain.
        return super()._check_double_validation_rules(employees, state)

    def _check_approval_update(self, state, raise_if_not_possible=True):
        if self.env.context.get('hlap_chain_final'):
            return True
        return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

    def _move_validate_leave_to_confirm(self):
        """ Override: going back to approval restarts the whole chain. """
        res = super()._move_validate_leave_to_confirm()
        self.sudo().write({
            'manager_approver_id': False, 'manager_approval_date': False,
            'hr_approver_id': False, 'hr_approval_date': False,
            'md_approver_id': False, 'md_approval_date': False,
        })
        return res

    #  CRON  #

    @api.model
    def _cron_remind_pending_approvals(self):
        """ Remind the approvers of requests that waited more than the configured delay. """
        now = fields.Datetime.now()
        rule_model = self.env['hr.attendance.rule']
        pending = self.search([('state', 'in', ('confirm', 'validate1'))])
        for leave in pending:
            if not leave.approval_stage:
                continue
            rule = rule_model._get_rule(leave.employee_id.company_id or self.env.company)
            waiting_since = max(filter(None, [
                leave.create_date,
                leave.manager_approval_date,
                leave.hr_approval_date,
            ]))
            if (now - waiting_since).days >= rule.reminder_days:
                leave._notify_current_stage(summary=_(
                    "Reminder: time off waiting for your approval (%s)",
                    dict(STAGES)[leave.approval_stage],
                ))
