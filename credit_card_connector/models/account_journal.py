from openerp import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    cc_processing = fields.Boolean(
        'CC Processing',
        help="Allow credit card processing in this journal.")
    cc_refunds = fields.Boolean(
        'CC Refunds',
        help="Allow credit card refunds in this journal.")
