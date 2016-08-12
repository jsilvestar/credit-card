from openerp import models, fields, api
from openerp.exceptions import except_orm, Warning
from lxml import etree
ENCRYPTED_FIELDS = ['cc_number', 'cc_cvv']


class cim_create_payment_profile(models.TransientModel):
    _name = 'cim.create.payment.profile'

    name = fields.Char('Name', size=255)
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True, readonly=True)
    cim_id = fields.Many2one(
        'customer.profile', 'Customer Profile', readonly=True, required=True)
    alt_invoice_addr_id = fields.Many2one(
        'res.partner', 'Billing Address', domain="['|',('parent_id','=',partner_id),('id','=',partner_id)]", help="An alternative contact to the default billing contact on the Customer Profile.")
    cc_number = fields.Char('CC Number', size=512, required=True)
    cc_cvv = fields.Char('Card Verification Value', size=512)
    cc_exp_month = fields.Char('Expiration Month', size=2, required=True)
    cc_exp_year = fields.Char('Expiration Year', size=4, required=True)
    bill_firstname = fields.Char('First Name', size=32)
    bill_lastname = fields.Char('Last Name', size=32)
    bill_street = fields.Char('Street', size=60)
    city_state_zip = fields.Char('City/State/Zip', size=128, readonly=True)
    payprofile_id = fields.Char('Payment Profile ID', size=32)
    manual = fields.Boolean()

    @api.onchange('alt_invoice_addr_id', 'cc_number', 'cim_id')
    def onchange_invoice(self):
        if self.cim_id:
            inv_rec = False
            if self.alt_invoice_addr_id:
                inv_rec = self.alt_invoice_addr_id
            else:
                inv_rec = self.cim_id.invoice_addr_id

            # Wait until CC is in to display other info, minor performance hack
            if inv_rec:
                self.cardholder_name = inv_rec.name

                # Fill out billing info with best guesses for first/last name, the rest
                # is just for show
                self.bill_firstname, _, self.bill_lastname = inv_rec.name.rpartition(
                    ' ')
                if not self.bill_firstname:
                    self.bill_firstname = self.bill_lastname
                    self.bill_lastname = False
                if inv_rec.street:
                    self.bill_street = inv_rec.street
                    if inv_rec.street2:
                        self.bill_street += ' ' + inv_rec.street2

                # Build up cosmetic city/state/zip field. If these are wrong, the contact
                # should be fixed, not the payment profile
                self.city_state_zip = inv_rec.city or ''
                if inv_rec.state_id:
                    self.city_state_zip = self.city_state_zip and self.city_state_zip + \
                        ', ' + inv_rec.state_id.code or inv_rec.state_id.code
                if inv_rec.zip:
                    self.city_state_zip += ' ' + inv_rec.zip

    @api.multi
    def add_existing_payment_profile(self):
        self = self.with_context(unmask=True)
        cc_info_read = self.read(ENCRYPTED_FIELDS)[0]

        if not self.cim_id.profile_id:
            raise Warning('Customer Profile has no valid ID!')
        # Generate document regarding payment profile
        name = self.name or self.alt_invoice_addr_id and self.alt_invoice_addr_id.name or self.cim_id.invoice_addr_id.name or False
        vals = {
            'name': name,
            'cim_id': self.cim_id.id,
            'last_four': cc_info_read['cc_number'][-4:],
            'cc_exp_month': self.cc_exp_month,
            'cc_exp_year': self.cc_exp_year,
            'payprofile_id': self.payprofile_id,
        }
        if self.alt_invoice_addr_id:
            vals['alt_invoice_addr_id'] = self.alt_invoice_addr_id.id
        cim_pay = self.env['payment.profile'].create(vals)

        return True

    # -------------
    # RSA Functions
    # -------------
    # Encrypt cc info for temporary storage in wizard record
    @api.model
    def create(self, values):
        if values.get('cc_number', False) and len(values['cc_number']) < 4:
            raise Warning(
                "Invalid credit card number")

        values = self.env['rsa.encryption'].rsa_create(
            values, secure_fields=ENCRYPTED_FIELDS)

        result = super(
            cim_create_payment_profile, self).create(values)
        return result

    # Mask data when reading
    # If context['unmask'] is True, return the fully decrypted values
    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]
        values = super(cim_create_payment_profile, self).read(
            cr, uid, ids, fields, context, load)

        return self.pool['rsa.encryption'].rsa_read(cr, uid, values, secure_fields=ENCRYPTED_FIELDS, context=context)

    # Don't write masked values to the database
    @api.multi
    def write(self, values):
        values = self.env['rsa.encryption'].rsa_write(
            values, secure_fields=ENCRYPTED_FIELDS)
        result = super(cim_create_payment_profile, self).write(values)
        return result

    # Strip out secured fields for duplication
    @api.one
    def copy(self, defaults):

        defaults = self.env['rsa.encryption'].rsa_copy(
            values=defaults, secure_fields=ENCRYPTED_FIELDS)

        return super(
            cim_create_payment_profile, self).copy(defaults)
