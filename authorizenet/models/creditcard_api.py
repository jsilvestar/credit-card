from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning
from lxml import etree
from urllib3 import HTTPSConnectionPool as pool
import time

# Stores authentication credentials
ENCRYPTED_FIELDS = ['login', 'key']


class credit_card_api(models.Model):
    _inherit = 'credit.card.api'

    url = fields.Char(
        'URL Path', required=True,
        size=256, default='/xml/v1/request.api',
        help="The path of the XML API URL.  Always begins with a leading slash.  The domain will be selected by the test mode checkbox.")

    # Prepare XML with credentials for our auth.net account - common to every request
    # Returns an lxml etree object with the root set to the root_string value
    @api.model
    def _get_xml_header(self, root_string, refId=False):
        if not root_string:
            raise except_orm(
                _('Programming Error'),
                _('No string defined for the root XML tag.'))

        auth_rec = self._get_encrypted_credentials()
        root = etree.Element(
            root_string,
            xmlns="AnetApi/xml/v1/schema/AnetApiSchema.xsd")
        merch_auth = etree.SubElement(root, 'merchantAuthentication')
        etree.SubElement(merch_auth, 'name').text = auth_rec.get('login')
        etree.SubElement(
            merch_auth, 'transactionKey').text = auth_rec.get('key')
        if refId:
            etree.SubElement(root, 'refId').text = str(refId)
        return root

    # Takes in an lxml etree object and returns the XML of the result
    @api.model
    def _send_request(self, req_xml_obj):
        auth_rec = self._get_credentials()

        # Domain is hardcoded, much less likely to change than the path
        if auth_rec.test:
            URL_DOMAIN = 'apitest.authorize.net'
        else:
            URL_DOMAIN = 'api2.authorize.net'
        TRANSIT_PATH = auth_rec.url

        # Open HTTPS pool
        https = pool(URL_DOMAIN, port=443)
        req = https.urlopen(
            'POST',
            TRANSIT_PATH,
            body=etree.tostring(req_xml_obj),
            headers={
                'content-type': 'text/xml'})
        res = False
        if req.status == 200:
            # 			print '\n\n\n',req.data,'\n\n\n'
            # Breaking namespaces specifically to make xpath not such a pain to
            # use
            res = etree.fromstring(
                req.data.replace(
                    ' xmlns=',
                    ' xmlnamespace='))
        else:
            raise Warning(
                _('Connection could not be completed to Authorize.net'))

        # Commit if Authorize.net request succeeds
        if res.xpath('//resultCode')[0].text == 'Ok':
            self._cr.commit()

        # Parse the response
        # Make sure the XML sent was valid
        if not self._context.get('from_transaction'):
            if res.xpath('//resultCode')[0].text != 'Ok':
                self._cr.rollback()
                errorcode = res.xpath('//messages/message/code')[-1].text
                errordesc = res.xpath('//messages/message/text')[-1].text
                errormsg = "Code - " + errorcode + "\n" + errordesc
                raise except_orm("There was an Error!", errormsg)

        # Looks valid, so return the XML text for function-specific parsing
        return res

    # Make sense of the payment gateway response data, a long comma-delimited text block
    # Takes in the root XML object and the string of the field the response is
    # in
    @api.model
    def _parse_payment_gateway_response(
            self, root_xml_obj, response_tag, unparsed_str=''):
        if not unparsed_str:
            response_locs = root_xml_obj.xpath('//' + response_tag)
            if not response_locs:
                print "Couldn't find '%s' in the response XML." % response_tag
                return False
            elif len(response_locs) > 1:
                print "Found more than one tag?? Something isn't right. '%s' may be the wrong tag." % response_tag
                return False
            unparsed_str = response_locs[0].text

        # See AIM guide (non-xml version) for explanation of field mapping starting at page 41
        # Note the importance of the empty map strings - Auth.net purposely leaves those fields
        # unused for future implementation without breaking the API by changing
        # the response length
        res_mapper = [
            'Response Code',
            'Response Subcode',
            'Response Reason Code',
            'Response Reason Text',
            'Authorization Code',
            'AVS Response',
            'Transaction ID',
            'Invoice Number',
            'Description',
            'Amount',
            'Method',
            'Transaction Type',
            'Customer ID',
            'First Name',
            'Last Name',
            'Company',
            'Address',
            'City',
            'State',
            'ZIP Code',
            'Country',
            'Phone',
            'Fax',
            'Email Address',
            'Ship To First Name',
            'Ship To Last Name',
            'Ship To Company',
            'Ship To Address',
            'Ship To City',
            'Ship To State',
            'Ship To ZIP Code',
            'Ship To Country',
            'Tax',
            'Duty',
            'Freight',
            'Tax Exempt',
            'Purchase Order Number',
            'MD5 Hash',
            'Card Code Response',
            'Cardholder Authentication Verification Response',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            'Account Number',
            'Card Type',
            'Split Tender ID',
            'Requested Amount',
            'Balance On Card',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
        ]

        res = {}
        split_response_list = unparsed_str.split(',')
        res_mapper_len = len(res_mapper)

        for item in res_mapper:
            if item:
                res[item] = split_response_list.pop(0) or False
            else:
                split_response_list.pop(0)
        return res


class PaymentProfile(models.Model):
    _inherit = 'payment.profile'

    # Delete entry on Auth.Net, then delete the payment profile locally
    @api.multi
    def cim_unlink(self):
        authnet_obj = self.env['credit.card.api']

        # Should only see one at a time, but be prepared for anything
        if not self.cim_id.profile_id:
            raise Warning(_('No payment profile ID available at Odoo'))
        root_obj = authnet_obj._get_xml_header(
            'deleteCustomerPaymentProfileRequest')
        etree.SubElement(
            root_obj,
            'customerProfileId').text = self.cim_id.profile_id
        etree.SubElement(
            root_obj,
            'customerPaymentProfileId').text = self.payprofile_id

        cim_id = self.cim_id.id
        # Delete locally - if the transaction failed, we'll raise an
        # exception and not reach this
        self.unlink()

        # Send response for each one
        response = authnet_obj._send_request(root_obj)

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

    # Modify expiration date for payment profile
    @api.multi
    def modify_expiry_date(self):
        authnet_obj = self.env['credit.card.api']

        # Should only see one at a time, but be prepared for anything
        for curr_rec in self:
            root_obj = authnet_obj._get_xml_header(
                'getCustomerPaymentProfileRequest')
            etree.SubElement(
                root_obj,
                'customerProfileId').text = curr_rec.cim_id.profile_id
            etree.SubElement(
                root_obj,
                'customerPaymentProfileId').text = curr_rec.payprofile_id

            # Send response for each one
            response = authnet_obj._send_request(root_obj)

            # Delete locally - if the transaction failed, we'll raise an
            # exception and not reach this
            self.unlink()
        return {}
