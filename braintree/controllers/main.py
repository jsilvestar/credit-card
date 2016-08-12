from braintree import ClientToken, PaymentMethod

from openerp import http, _
from openerp.http import request

import werkzeug
from werkzeug import url_encode


class website_braintree(http.Controller):

    @http.route("/braintree/checkout/partner/<model('res.partner'):partner>/", type='http', method='get', auth='public', website=True)
    def output_controller(self, partner, **kwargs):
        payment_method_nonce = kwargs.get('payment_method_nonce')
        if partner.cim_id:
            customer_id = partner.cim_id.profile_id
        else:
            raise Warning(_('Customer not available in Braintree'))

        # Configure braintree environment
        request.env['credit.card.api']._configure_environment()
        if not partner.braintree_address_id:
            request.env['cim.create.customer.profile'].create_braintree_address(partner)
        result = PaymentMethod.create({
            "customer_id": customer_id,
            "payment_method_nonce": payment_method_nonce,
            "billing_address_id": partner.braintree_address_id,
            "options": {
                "verify_card": True
            }
        })
        if not result.is_success:
            raise Warning(result.message)

        payment_profile_obj = request.env['payment.profile']
        values = payment_profile_obj._prepare_payment_method(
            result.payment_method, partner)
        payment_profiles = payment_profile_obj.search(
            [('payprofile_id', '=', result.payment_method.token)])
        if not payment_profiles:
            payment_profiles = payment_profile_obj.create(values)
        else:
            payment_profiles.write(values)

        action_id = kwargs.get('action', False)
        if kwargs.get('model', False) in ['sale.order', 'account.invoice']:
            request.env[kwargs.get('model')].browse(
                int(kwargs.get('id'))).cim_payment_id = payment_profiles.id
            if kwargs.get('model', False) == 'sale.order':
                action_xml_id = 'sale.action_orders'
            elif kwargs.get('model', False) == 'account.invoice':
                action_xml_id = 'account.action_invoice_tree1'
            action_id = request.env.ref(action_xml_id).id

        return werkzeug.utils.redirect('/web?debug=#model=%s&id=%s&action=%s&view_type=form' % (kwargs.get('model', False), kwargs.get('id', False), action_id))

    @http.route("/braintree/partner/<model('res.partner'):partner>/", method="get", auth='public', website=True)
    def input_controller(self, partner, **kwargs):
        if partner.cim_id:
            customer_id = partner.cim_id.profile_id
            # Configure braintree environment
            request.env['credit.card.api']._configure_environment()
            client_token = ClientToken.generate({
                "customer_id": customer_id
            })
        else:
            raise Warning(_('Customer not available in Braintree'))
        url = '/braintree/checkout/partner/%s/?%s' % (
            partner.id, url_encode(kwargs))
        return request.website.render("braintree.simple_page",
                                      {'token': client_token, 'partner': partner, 'url': url})
