import logging
_logger = logging.getLogger(__name__)
import string
import re

from openerp import models, fields, api, _
from openerp.exceptions import UserError, except_orm, Warning
from lxml import etree
from openerp import netsvc
from openerp.osv.orm import setup_modifiers

ENCRYPTED_FIELDS = ['cc_number', 'cc_cvv', 'cc_exp_month', 'cc_exp_year']


class account_payment(models.Model):
    _inherit = 'account.payment'

    use_cc = fields.Boolean('Use CC', copy=False)
    new_card = fields.Boolean('New Credit card', copy=False)
    show_new_card = fields.Boolean(copy=False)
    invoice_addr_id = fields.Many2one(
        'res.partner',
        'Invoice Address',
        domain="['|',('partner_id','=',parent_id)('partner_id','=',id)]", copy=False)
    last_four = fields.Char(
        'Paid with card ending', size=4, readonly=True, copy=False)
    cc_number = fields.Char('CC Number', size=512, copy=False)
    cc_cvv = fields.Char('CVV', size=512, copy=False)
    cc_exp_month = fields.Char('Expiration Month', size=512, copy=False)
    cc_exp_year = fields.Char('Expiration Year', size=512, copy=False)
    bill_firstname = fields.Char('First Name', size=32, copy=False)
    bill_lastname = fields.Char('Last Name', size=32, copy=False)
    bill_street = fields.Char('Street', size=60, copy=False)
    city_state_zip = fields.Char('City/State/Zip', size=128, copy=False)
    transId = fields.Char(
        'Transaction ID',
        size=128, copy=False,
        readonly=True)
    is_approved = fields.Boolean('Approved', readonly=True)
    state = fields.Selection(
        [('draft', 'Draft'),
         ('posted', 'Posted'),
         ('sent', 'Sent'),
         ('reconciled', 'Reconciled')],
        readonly=True, default='draft', copy=False, string="Status")
    cim_id = fields.Many2one(
        'customer.profile',
        'Customer Profile', copy=False,
        domain="[('partner_id','=',partner_id)]")
    cim_payment_id = fields.Many2one(
        'payment.profile',
        'Card on File', copy=False,
        domain="[('cim_id','=',cim_id)]")
    transaction_ids = fields.One2many(
        'credit.card.transaction',
        'payment_id', copy=False,
        string='CC Transaction',
        readonly=True)

    @api.model
    def get_cc_profile(self):
        value = {}
        self.new_card = False
        if self.partner_id.cim_id:
            self.cim_id = self.partner_id.cim_id.id
            # Grab the default payment profile
            if self.partner_id.cim_id.default_payprofile_id and not self.cim_payment_id:
                self.cim_payment_id = self.partner_id.cim_id.default_payprofile_id.id
            # If no default, grab the first profile we find
            elif self.partner_id.cim_id.payprofile_ids and not self.cim_payment_id:
                self.cim_payment_id = self.partner_id.cim_id.payprofile_ids[
                    0].id
            elif self.cim_payment_id:
                pass
            else:
                self.new_card = True
        else:
            self.new_card = True
        return value

    @api.onchange('use_cc', 'invoice_addr_id', 'new_card')
    def onchange_invoice(self):
        self.bill_firstname = False
        self.bill_lastname = False
        self.bill_street = False
        self.city_state_zip = False

        if self.new_card:
            self.cim_payment_id = False
        if self.use_cc and self.invoice_addr_id:
            # Fill out billing info with best guesses for first/last name, the rest
            # is just for show
            self.bill_firstname, _, self.bill_lastname = self.invoice_addr_id.name.rpartition(
                ' ')
            if not self.bill_firstname:
                self.bill_firstname = self.bill_lastname
                self.bill_lastname = False
            if self.invoice_addr_id.street:
                self.bill_street = self.invoice_addr_id.street
                if self.invoice_addr_id.street2:
                    self.bill_street += ' ' + self.invoice_addr_id.street2

            self.city_state_zip = self.invoice_addr_id.city or ''
            if self.invoice_addr_id.state_id:
                self.city_state_zip = self.city_state_zip + ', ' + \
                    self.invoice_addr_id.state_id.code or self.invoice_addr_id.state_id.code
            if self.invoice_addr_id.zip:
                self.city_state_zip += ' ' + self.invoice_addr_id.zip

    @api.onchange('journal_id')
    def _onchange_journal(self):
        res = super(account_payment, self)._onchange_journal()
        self.use_cc = self.journal_id and self.journal_id.cc_processing
        if self.use_cc and self.partner_id:
            self.show_new_card = self.env[
                'credit.card.api']._get_credentials().create_creditcard_payment
            self.get_cc_profile()
        if not self.use_cc:
            self.cim_id = False
            self.cim_payment_id = False
            self.show_new_card = False
        return res

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if not self._context.get('default_invoice_addr_id', False):
            addrs = self.partner_id.address_get(['invoice'])
            self.invoice_addr_id = addrs.get('invoice', False) and addrs['invoice'] or \
                addrs.get('default', False) and addrs['default'] or \
                False
        if self.journal_id.cc_processing and self.partner_id:
            self.get_cc_profile()
        else:
            self.cim_id = False
            self.cim_payment_id = False
            self.new_card = False

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        res = super(account_payment, self)._onchange_payment_type()
        if self.payment_type not in ['inbound']:
            res['domain']['journal_id'].extend(
                ['|', ('cc_processing', '=', False), ('cc_refunds', '=', False)])
        return res

    # Encrypt data for temporary storage (before validating)
    @api.model
    def create(self, values):
        # Only do cleaning if it's a CC processing journal, otherwise strip any
        # leftover data
        journal_rec = self.env['account.journal'].browse(values['journal_id'])
        if journal_rec.cc_processing:
            # Strip out any non-digit characters first
            for field in ENCRYPTED_FIELDS:
                if not values[field]:
                    del values[field]
                else:
                    values[field] = re.sub(r'\D', '', values[field])
            if ENCRYPTED_FIELDS:
                values = self.env['rsa.encryption'].rsa_create(
                    values,
                    ENCRYPTED_FIELDS)
        else:
            for field in ENCRYPTED_FIELDS:
                if field in values:
                    del values[field]
        return super(account_payment, self).create(values)

    # Don't write masked values to the database
    @api.multi
    def write(self, values):
        values = self.env['rsa.encryption'].rsa_write(values, ENCRYPTED_FIELDS)
        return super(account_payment, self).write(values)

    # Mask data when reading
    # Use context['unmask'] = True before making read() call to return fully unmasked values
    # OR, use context['cc_last_four'] = True to return the unmasked last 4
    # digits of the CC number
    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        if context is None:
            context = {}
        values = super(account_payment, self).read(
            cr, uid, ids, fields, context, load)
        ctx = {}
        ctx.update(context)
        ctx['cc_last_four'] = True
        return self.pool['rsa.encryption'].rsa_read(cr, uid, values, ENCRYPTED_FIELDS, ctx)

    # Delete any potential CC data when copying
    @api.one
    def copy(self, defaults):
        defaults = self.env['rsa.encryption'].rsa_copy(
            defaults, ENCRYPTED_FIELDS)
        return super(account_payment, self).copy(defaults)

    @api.multi
    def create_customer_profile(self):
        cust_profile = self.env['cim.create.customer.profile']
        for record in self:
            new_cim = cust_profile.create({'name': record.partner_id.name,
                                           'partner_id': record.partner_id.id,
                                           'invoice_addr_id': record.invoice_addr_id.id})
            cim_id = new_cim.send_request()
            if cim_id:
                self.cim_id = new_cim.id
                self._cr.commit()
        return True

    @api.multi
    def create_payment_profile(self):
        vals = {}
        pay_profile = self.env['cim.create.payment.profile']
        for record in self:
            record = record.with_context(unmask=True)
            cc_info = record.read(ENCRYPTED_FIELDS)[0]
            record = record.with_context(unmask=False)
            vals['name'] = record.partner_id.name
            vals['partner_id'] = record.partner_id.id
            vals['alt_invoice_addr_id'] = record.invoice_addr_id.id
            vals['cc_number'] = cc_info['cc_number']
            vals['cc_exp_month'] = cc_info['cc_exp_month']
            vals['cc_exp_year'] = cc_info['cc_exp_year']
            vals['bill_firstname'] = record.bill_firstname
            vals['bill_lastname'] = record.bill_lastname
            vals['bill_street'] = record.bill_street
            vals['city_state_zip'] = record.city_state_zip
            vals['cim_id'] = record.partner_id.cim_id.id
            new_profile_id = pay_profile.create(vals)
            profile_id = new_profile_id.send_request()
            if profile_id:
                self.write(
                    {'cim_payment_id': profile_id.id, 'new_card': False})
                self._cr.commit()
        return True

    @api.multi
    def cancel(self):
        for rec in self:
            if rec.use_cc and rec.cc_number:
                rec.write({
                    'cc_number': False,
                    'cc_cvv': False,
                    'cc_exp_month': False,
                    'cc_exp_year': False,
                })
        return super(
            account_payment, self).cancel()
