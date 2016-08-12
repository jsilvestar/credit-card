from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning
from lxml import etree
from urllib3 import HTTPSConnectionPool as pool
import time

# Stores authentication credentials
ENCRYPTED_FIELDS = ['gateway_id', 'login', 'key']


class credit_card_api(models.Model):
    _name = 'credit.card.api'

    name = fields.Char(size=64, required=True,
                       help="Identifying name for these credentials.")
    active = fields.Boolean('Active', default=True)
    test = fields.Boolean('Test Mode')
    gateway_id = fields.Char(
        'Payment Gateway ID',
        size=512,
        required=True)
    login = fields.Char(
        'API Login ID',
        size=512,
        required=True)
    key = fields.Char(
        'Transaction Key',
        size=512,
        required=True)
    create_creditcard_payment = fields.Boolean('Add credit card profile from Payment window',
                                               help="This option enables to create a new payment profile at Payment window")
    create_profile = fields.Boolean('Always create profile', default=True)

    # Get the braintree credentials to use, returns a browse_record object
    @api.model
    def _get_credentials(self):
        self = self.with_context(unmask=True)
        auth_rec = self.search([('active', '=', True)], limit=1)
        if not auth_rec._ids:
            raise Warning(_('No credit card credentials found!'))
        return auth_rec[0]

    @api.model
    def _get_encrypted_credentials(self):
        self = self.with_context(unmask=True)
        auth_rec = self.search_read([('active', '=', True)], limit=1)
        if len(auth_rec) < 1:
            raise Warning(_('No credit card credentials found!'))
        return auth_rec[0]

    # Encrypt login key for security purposes
    @api.model
    def create(self, values):
        values = self.env['rsa.encryption'].rsa_create(
            values, secure_fields=ENCRYPTED_FIELDS)
        return super(credit_card_api, self).create(values)

    # Mask data when reading
    # If context['unmask'] is True, return the fully decrypted values
    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]
        values = super(credit_card_api, self).read(
            cr, uid, ids, fields, context, load)

        return self.pool['rsa.encryption'].rsa_read(cr, uid, values, secure_fields=ENCRYPTED_FIELDS, context=context)

    # Don't write masked values to the database
    @api.multi
    def write(self, values):
        values = self.env['rsa.encryption'].rsa_write(
            values, secure_fields=ENCRYPTED_FIELDS)
        return super(
            credit_card_api, self).write(values)

    # Strip out secured fields for duplication
    @api.one
    def copy(self, defaults):
        defaults = self.env['rsa.encryption'].rsa_copy(
            values=defaults, secure_fields=ENCRYPTED_FIELDS)
        return super(credit_card_api, self).copy(defaults)


class CustomerProfile(models.Model):
    _name = 'customer.profile'
    _description = "Customer Information Manager"

    name = fields.Char(
        'Name',
        size=64,
        readonly=True)
    profile_id = fields.Char(
        'Customer Profile ID',
        size=32)
    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
        readonly=True,
        required=True)
    invoice_addr_id = fields.Many2one(
        'res.partner',
        'Invoice Contact',
        readonly=True,
        required=True)
    payprofile_ids = fields.One2many(
        'payment.profile',
        'cim_id',
        'Payment Profiles',
        readonly=True)
    transaction_ids = fields.One2many(
        'credit.card.transaction',
        'cim_id',
        'Payment History',
        readonly=True)
    default_payprofile_id = fields.Many2one(
        'payment.profile',
        'Default Payment Profile',
        domain="[('cim_id','=',id)]",
        help="Load this record by default when registering a payment. Won't prevent access to other payment profiles.")

    # Launches the wizard to create a payment profile to link to this customer
    @api.multi
    def create_payment_profile(self):
        # Start the wizard by returning an action dictionary, defaulting in the
        # partner_id
        self = self.with_context({
            'default_partner_id': self.partner_id.id,
            'default_cim_id': self.id,
            'default_alt_invoice_addr_id': self.invoice_addr_id.id,
            'cc_last_four': True
        })
        name = 'Register a Payment Profile'
        if self._context.get('default_manual', False):
            name = 'Add an Existing Payment Profile'

        return {
            'name': name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'cim.create.payment.profile',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': self._context,
        }

    @api.multi
    def link_payment_profiles(self):
        return {
            'name': 'Payment Profiles',
            'view_type': 'form',
            'view_mode': 'tree, form',
            'domain': [('cim_id', '=', self.id)],
            'res_model': 'payment.profile',
            'view_id': False,
            'views': [(False, 'tree'),
                      (False, 'form')],
            'type': 'ir.actions.act_window',
            'target': 'current',
        }


class PaymentProfile(models.Model):
    _name = 'payment.profile'
    _description = "Customer Payment Profiles for credit card CIM"

    name = fields.Char(
        'Name',
        size=64,
        readonly=True)
    payprofile_id = fields.Char(
        'Payment Profile ID',
        size=32)
    cim_id = fields.Many2one(
        'customer.profile',
        'Customer Profile',
        readonly=True,
        required=True)
    last_four = fields.Char(
        'Last Four of CC',
        size=4)
    alt_invoice_addr_id = fields.Many2one(
        'res.partner',
        'Alternate Billing Contact',
        readonly=True,
        help="An alternative contact to the default billing contact on the Customer Profile.")
    cc_exp_month = fields.Char(
        'Expiration Month',
        size=2)
    cc_exp_year = fields.Char(
        'Expiration Year',
        size=2)
    active = fields.Boolean(default=True)

    @api.multi
    def name_get(self):
        res = []
        for r in self.read(['name', 'last_four', 'cc_exp_month', 'cc_exp_year']):
            res.append(
                (r['id'], 'CC: %s - %s %s/%s' % (r['last_four'], r['name'], r['cc_exp_month'], r['cc_exp_year'])))
        return res


class credit_card_transaction(models.Model):
    _name = 'credit.card.transaction'
    _rec_name = 'trans_id'

    trans_id = fields.Char(
        'Transaction ID',
        size=30)
    cim_id = fields.Many2one(
        'customer.profile',
        'Customer Profile')
    pim_id = fields.Many2one(
        'payment.profile',
        'Payment Profile')
    amount = fields.Float('Amount transferred')
    invoice_id = fields.Many2one(
        'account.invoice',
        'Invoice')
    sale_id = fields.Many2one(
        'sale.order',
        'Sales Order Ref')
    payment_id = fields.Many2one(
        'account.payment',
        'Payment')
    trans_date = fields.Datetime(
        'Transaction Date & Time',
        default=lambda *a: time.strftime('%Y-%m-%d %H:%M:%S'),
        readonly=True)
    message = fields.Char(
        'Message',
        size=300)
    authCode = fields.Char(
        'Authorization Code',
        size=6)
    avsResultCode = fields.Char(
        'AVS Result',
        size=300)
    cvvResultCode = fields.Char(
        'CVV Result',
        size=300)
    card_type = fields.Char(
        'Card Type',
        size=16,
        help="The type of card used to pay.  Visa, MasterCard, American Express, etc.")

    _order = 'trans_date desc'
