from openerp import models, fields


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    is_cc_term = fields.Boolean('CC Term?')
