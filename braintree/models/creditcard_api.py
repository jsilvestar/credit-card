from braintree import Environment, Configuration, PaymentMethod, Customer
# import time

from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning
from lxml import etree
from urllib3 import HTTPSConnectionPool as pool
import time

# Stores authentication credentials
ENCRYPTED_FIELDS = ['login', 'key']


class credit_card_api(models.Model):
    _inherit = 'credit.card.api'

    gateway_id = fields.Char('Mercant ID')
    login = fields.Char('Public Key')
    key = fields.Char('Private Key')

    @api.model
    def _configure_environment(self):
        creditcard_api = self._get_encrypted_credentials()
        if creditcard_api.get('test'):
            environment = Environment.Sandbox
        else:
            environment = Environment.Production
        Configuration.configure(environment,
                                merchant_id=creditcard_api.get('gateway_id'),
                                public_key=creditcard_api.get('login'),
                                private_key=creditcard_api.get('key'))


class CustomerProfile(models.Model):
    _inherit = 'customer.profile'

    @api.model
    def create_customer_profile(self, partner):
        cust_profile = self.env['cim.create.customer.profile']
        new_cim = cust_profile.create({
           'name': partner.name,
           'partner_id': partner.id,
           'invoice_addr_id': partner.id
        })
        cim_id = new_cim.send_request()
        return True

    @api.model
    def add_existing_customer_profile(self, partner, profile_id):
        cust_profile = self.env['cim.create.customer.profile']
        new_cim = cust_profile.create({
           'name': partner.name,
           'partner_id': partner.id,
           'invoice_addr_id': partner.id,
           'profile_id': profile_id,
        })
        cim_id = new_cim.add_existing_customer_profile()
        return True

class PaymentProfile(models.Model):
    _inherit = 'payment.profile'

    # Delete entry on Auth.Net, then delete the payment profile locally
    @api.multi
    def cim_unlink(self):
        # Should only see one at a time, but be prepared for anything
        if not self.cim_id.profile_id:
            raise Warning(_('No customer profile ID available at Odoo'))

        cim_id = self.cim_id.id
        payprofile_id = self.payprofile_id
        # Delete locally - if the transaction failed, we'll raise an
        # exception and not reach this
        self.unlink()

        self.env['credit.card.api']._configure_environment()

        result = PaymentMethod.delete(payprofile_id)
        if not result.is_success:
            raise Warning(result.message)

        return {
            'name': 'Payment Profiles',
            'view_type': 'form',
            'view_mode': 'tree, form',
            'domain': [('cim_id', '=', cim_id)],
            'res_model': 'payment.profile',
            'view_id': False,
            'views': [(False, 'tree'),
                      (False, 'form')],
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def _prepare_payment_method(self, payment_method, partner):
        return {
            'name': partner.name,
            'payprofile_id': payment_method.token,
            'cim_id': partner.cim_id.id,
            'last_four': payment_method.last_4,
            'alt_invoice_addr_id': partner.id,
            'cc_exp_month': payment_method.expiration_month,
            'cc_exp_year': payment_method.expiration_year and payment_method.expiration_year[-2:]
        }

    @api.multi
    def update_all_payment_methods(self, partner):
        # Configure braintree environment
        self.env['credit.card.api']._configure_environment()
        result = Customer.find(partner.cim_id.profile_id)
        payment_profiles = partner.cim_id.payprofile_ids
        for payment_method in result.payment_methods:
            values = self._prepare_payment_method(
                payment_method, partner)
            profile = payment_profiles.filtered(
                lambda r: r.payprofile_id == payment_method.token)
            if not profile:
                profile = self.env['payment.profile'].create(values)
            else:
                payment_profiles = payment_profiles - profile
                profile.write(values)
            if payment_method.default:
                profile.cim_id.default_payprofile_id = profile.id

        # Set active=False for inactive payment_method record in Odoo
        if payment_profiles:
            payment_profiles.write({'active': False})
