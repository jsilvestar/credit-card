from openerp import models, fields, api


class account_invoice(models.Model):
    _inherit = 'account.invoice'

    is_cc_payment = fields.Boolean('Use CC Payment')

    @api.onchange('payment_term_id')
    def onchange_payment_term_cc(self):
        self.is_cc_payment = self.payment_term_id.is_cc_term

    @api.multi
    def invoice_pay_customer(self):
        if not self._ids:
            return []
        action = self.env.ref(
            'account.action_account_invoice_payment').read()[0]
        context = {'default_invoice_ids': [(4, self.id, None)]}
        context['record_id'] = self.id

        # Check for a default invoice address. If there's a default invoice
        # address, pass the id to the next screen even if it's not for CC payments.
        # TODO: This should be moved outside of the scope of this module!
        context['default_invoice_addr_id'] = self.partner_id.id

        # Load cc_processing journal if its respective payment term is loaded.
        if self.is_cc_payment:
            journal = self.env['account.journal'].search(
                [('cc_processing', '=', True)], limit=1)
            if journal:
                context['default_journal_id'] = journal.id
            action['name'] = 'Pay Invoice by Credit Card'
        action['context'] = context
        return action
