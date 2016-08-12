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

    # Prepare an XML request to send validating the transaction
    @api.multi
    def _prepare_transaction_request(self):
        self = self.with_context(unmask=True)
        ref_orders = self.payment_reference or ''
        ref_credit_memos = self.payment_reference or ''
        cust_info = {}

        # ------------------------
        # Begin the XML generation
        # ------------------------
        # Format will vary based on if it's a card on file or one-time use
        # local card

        # Card on file
        if self.cim_payment_id:
            refId = self.id
            root = self.env['credit.card.api']._get_xml_header(
                'createCustomerProfileTransactionRequest', refId)

            self = self.with_context(unmask=True)
            cc_read = self.read(ENCRYPTED_FIELDS)[0]

            # Transaction type and amount
            transaction = etree.SubElement(root, 'transaction')
            auth_capture = etree.SubElement(
                transaction, 'profileTransAuthCapture')
            etree.SubElement(
                auth_capture, 'amount').text = str(self.amount)
            etree.SubElement(
                auth_capture, 'customerProfileId').text = self.cim_id.profile_id
            etree.SubElement(
                auth_capture, 'customerPaymentProfileId').text = self.cim_payment_id.payprofile_id
            if self.cc_cvv:
                etree.SubElement(
                    auth_capture, 'cardCode').text = cc_read['cc_cvv']

        # One-time use card
        else:
            # Need to gather additional data about the payment first
            # If the invoice address isn't filled in or is missing data, get
            # the company instead
            cust_info['id'] = self.invoice_addr_id.id or self.partner_id.id
            cust_info[
                'email'] = self.invoice_addr_id.email or self.partner_id.email or ''

            namepart = self.invoice_addr_id.name.rpartition(' ')
            cust_info['firstName'] = namepart[0]
            cust_info['lastName'] = namepart[2]
            cust_info['company'] = self.partner_id.name
            cust_info[
                'address'] = self.invoice_addr_id.street or self.partner_id.street or ''
            cust_info[
                'city'] = self.invoice_addr_id.city or self.partner_id.city or ''
            cust_info[
                'state'] = self.invoice_addr_id.state_id.code or self.partner_id.state_id.code or ''
            cust_info[
                'zip'] = self.invoice_addr_id.zip or self.partner_id.zip or ''
            cust_info[
                'country'] = self.invoice_addr_id.country_id.name or self.partner_id.country_id.name or ''

            full_str = string.maketrans('', '')
            nodigs = full_str.translate(full_str, string.digits)
            phone_num = self.invoice_addr_id.phone or self.partner_id.phone or ''
            if phone_num:
                cust_info['phoneNumber'] = str(
                    phone_num).translate(full_str, nodigs)
            fax_num = self.invoice_addr_id.fax or self.partner_id.fax or ''
            if fax_num:
                cust_info['faxNumber'] = str(
                    fax_num).translate(full_str, nodigs)

            # Start generating the XML
            refId = self.id
            root = self.env['credit.card.api']._get_xml_header(
                'createTransactionRequest', refId)

            # Transaction type and amount
            transaction_req = etree.SubElement(root, 'transactionRequest')
            etree.SubElement(
                transaction_req, 'transactionType').text = 'authCaptureTransaction'
            etree.SubElement(
                transaction_req, 'amount').text = str(self.amount)

            # Payment info
            # Prep info dictionary for the XML tree
            cc_info = self.read(ENCRYPTED_FIELDS)[0]

            pay_type = etree.SubElement(transaction_req, 'payment')
            cc = etree.SubElement(pay_type, 'creditCard')
            etree.SubElement(cc, 'cardNumber').text = cc_info['cc_number']
            etree.SubElement(
                cc, 'expirationDate').text = cc_info['cc_exp_month'] + '/' + cc_info['cc_exp_year']
            if cc_info.get('cc_cvv'):
                etree.SubElement(cc, 'cardCode').text = cc_info['cc_cvv']
            del cc_info

            # Reference info
            order_ref = etree.SubElement(transaction_req, 'order')
            etree.SubElement(order_ref, 'invoiceNumber').text = ref_orders
            if ref_credit_memos:
                etree.SubElement(
                    order_ref, 'description').text = 'Credit memo(s) applied from: ' + ref_credit_memos

            # Customer record, using partner ID as custom id (contact/partner
            # IDs don't overlap anymore in 7.0!)
            cust = etree.SubElement(transaction_req, 'customer')
            etree.SubElement(cust, 'id').text = str(cust_info['id'])
            if cust_info['email']:
                etree.SubElement(cust, 'email').text = cust_info['email']

            # Bill To info
            billto = etree.SubElement(transaction_req, 'billTo')
            etree.SubElement(billto, 'firstName').text = cust_info['firstName']
            if cust_info['lastName']:
                etree.SubElement(
                    billto, 'lastName').text = cust_info['lastName']
            etree.SubElement(billto, 'company').text = cust_info['company']
            if cust_info['address']:
                etree.SubElement(billto, 'address').text = cust_info['address']
            if cust_info['city']:
                etree.SubElement(billto, 'city').text = cust_info['city']
            if cust_info['state']:
                etree.SubElement(billto, 'state').text = cust_info['state']
            etree.SubElement(billto, 'zip').text = cust_info['zip']
            if cust_info['country']:
                etree.SubElement(billto, 'country').text = cust_info['country']
            if cust_info.get('phoneNumber', False):
                etree.SubElement(
                    billto, 'phoneNumber').text = cust_info['phoneNumber']
            if cust_info.get('faxNumber', False):
                etree.SubElement(
                    billto, 'faxNumber').text = cust_info['faxNumber']

            # Define as ecommerce transaction (card not present)
            retail = etree.SubElement(transaction_req, 'retail')
            etree.SubElement(retail, 'marketType').text = '0'

        print etree.tostring(root, pretty_print=True)
        return root

    @api.multi
    def post(self):
        credit_transaction_obj = self.env['credit.card.transaction']
        trans_vals = {}
        payment_vals = {}

        for record in self:
            # Make sure there's an amount, $0 payments are worthless!
            if not record.amount:
                raise UserError(
                    '_(Paid Amount is $0, please enter a payment amount.)')

            if record.new_card:
                if not (
                        record.cc_number and record.cc_exp_month and record.cc_exp_year):
                    raise UserError(
                        _('Provide credit card details for Transaction'))
            if record.use_cc:
                if not record.cim_payment_id and not record.new_card:
                    raise UserError(
                        _('Select or create a Payment profile'))
                # When 'Always create profile' boolean field is selected at
                # API credential configuration, the customer profile and
                # payment profile is created before sending info to
                # authorize.net
                search_ids = self.env['credit.card.api'].search(
                    [('create_profile', '=', True)])
                if search_ids:
                    if not record.cim_id:
                        self.create_customer_profile()
                    if record.new_card:
                        self.create_payment_profile()

        for payment in self.browse(self._ids):
            # Process the valid id list
            try:
                res = super(account_payment, self).post()
            except Exception as e:
                self._cr.rollback()
                raise e

            # If this is a CC payment, authenticate with Authorize.net
            if payment.use_cc:
                # Prepare documents required for transaction processing
                self.last_four = payment.cim_payment_id.last_four
                # Transaction object record is created here
                invoice_id = self._context.get('record_id')
#                 self._cr.execute(
#                     "select order_id from sale_order_invoice_rel where invoice_id=%s", (invoice_id,))
#                 sale_list = map(lambda x: x[0], self._cr.fetchall())
                sale_id = False
#                 if sale_list:
#                     sale_id = sale_list[0]
                trans_vals = {
                    'cim_id': payment.cim_id.id,
                    'pim_id': payment.cim_payment_id.id,
                    'amount': payment.amount,
                    'invoice_id': invoice_id,
                    'sale_id': sale_id,
                    'payment_id': payment.id
                }
                transaction_rec = credit_transaction_obj.create(trans_vals)

                # Prepare the XML request
                req_xml_obj = self._prepare_transaction_request()

                # Send the XML object to Authorize.net and return an XML
                # object of the response
                authnet_obj = self.env['credit.card.api']
                self = self.with_context(from_transaction=payment.id)
                res = authnet_obj._send_request(req_xml_obj)

                _logger.info(etree.tostring(res, pretty_print=True))

                if not res.xpath('//directResponse'):
                    errorcode = res.xpath(
                        '//messages/message/code')[-1].text
                    errordesc = res.xpath(
                        '//messages/message/text')[-1].text
                    errormsg = "Code - " + errorcode + "\n" + errordesc
                    self._cr.rollback()
                    raise except_orm(
                        'There seems to be an error !', errormsg)

                # Parsing will vary depending on if it's a card on file or
                # one-time card
                if payment.cim_payment_id:
                    res_dict = authnet_obj._parse_payment_gateway_response(
                        res, 'directResponse')
                    approval_code = res_dict['Response Code']
                    transId = res_dict['Transaction ID']
                    errordesc = res_dict['Response Reason Text']
                    errorid = res_dict['Response Reason Code']
                    card_type = res_dict['Card Type']
                    authCode = res_dict['Authorization Code']
                    avsResultCode = res_dict['AVS Response']
                    cvvResultCode = res_dict['Card Code Response']
                else:
                    # Get the transaction approval code
                    approval_code = res.xpath('//responseCode')[0].text

                    transId_loc = res.xpath('//transId')
                    transId = transId_loc and transId_loc[0].text or False
                    errorcode_loc = res.xpath('//errorcode')
                    errorid = errorcode_loc and errorcode_loc[0].text or False
                    error_loc = res.xpath('//errorText')
                    errordesc = error_loc and error_loc[0].text or False
                    card_type_loc = res.xpath('//accountType')
                    card_type = card_type_loc and card_type_loc[
                        0].text or False
                    auth_code_loc = res.xpath('//authCode')
                    authCode = auth_code_loc and auth_code_loc[0].text or False
                    avs_response_loc = res.xpath('//avsResponse')
                    avsResultCode = avs_response_loc and avs_response_loc[
                        0].text or False
                    card_code_loc = res.xpath('//cardCode')
                    cvvResultCode = card_code_loc and card_code_loc[
                        0].text or False

                CARD_CODE_RESPONSE = {
                    'M': 'Match',
                    'N': 'No Match',
                    'P': 'Not Processed',
                    'S': 'Should have been present',
                    'U': 'Issuer unable to process request',
                }
                AVS_RESPONSE = {
                    'A': 'Address (Street) matches, ZIP does not',
                    'B': 'Address information not provided for AVS check',
                    'E': 'AVS error',
                    'G': 'Non-U.S. Card Issuing Bank',
                    'N': 'No Match on Address (Street) or ZIP',
                    'P': 'AVS not applicable for this transaction',
                    'R': 'Retry-System unavailable or timed out',
                    'S': 'Service not supported by issuer',
                    'U': 'Address information is unavailable',
                    'W': 'Nine digit ZIP matches, Address (Street) does not',
                    'X': 'Address (Street) and nine digit ZIP match',
                    'Y': 'Address (Street) and five digit ZIP match',
                    'Z': 'Five digit ZIP matches, Address (Street) does not',
                }
                if cvvResultCode in ['M', 'N', 'P', 'S', 'U']:
                    cvvResultCode = CARD_CODE_RESPONSE[cvvResultCode]
                if avsResultCode in ['A', 'B', 'E', 'G', 'N', 'P', 'R', 'S', 'U', 'W', 'X', 'Y', 'Z']:
                    avsResultCode = AVS_RESPONSE[avsResultCode]
                trans_update = {
                    'trans_id': transId,
                    'message': errordesc,
                    'card_type': card_type,
                    'authCode': authCode,
                    'avsResultCode': avsResultCode,
                    'cvvResultCode': cvvResultCode}
                trans_vals.update(trans_update)

                # If the record had one-time-use CC data, we can clear it now.  It should have
                # already validated/failed from the proforma_payment function, so we don't have
                # to worry about deleting CC data prematurely.
                # Used a CC and there is a cc_number (wasn't in some way on
                # file)
                if payment.use_cc:
                    payment_vals = {
                        'cc_number': False,
                        'cc_cvv': False,
                        'cc_exp_month': False,
                        'cc_exp_year': False,
                    }
                if approval_code == '1':
                    payment_vals['is_approved'] = True
                    payment_vals['transId'] = transId
                    self.write(payment_vals)
                    transaction_rec.write(trans_update)
                    self._cr.commit()
                else:
                    self._cr.rollback()
                    new_error_transaction = self.env[
                        'credit.card.transaction'].create(trans_vals)
                    payment_vals['is_approved'] = False
                    payment_vals['last_four'] = ''
                    self.write(payment_vals)
                    message_to_display = 'Error code - ' + \
                        errorid + "\n" + errordesc
                    if approval_code == '2':
                        message_header = 'Credit card was declined '
                    elif approval_code == '3':
                        message_header = 'There was an error '
                    else:
                        message_header = 'The transaction was held for review '
                    raise except_orm(message_header, message_to_display)
        return True

    @api.multi
    def _prepare_void_request(self):
        # Start root tag and add credentials
        root = self.env['credit.card.api']._get_xml_header(
            'createTransactionRequest', self.id)

        # Void request, adding transaction ID to void
        transaction_req = etree.SubElement(root, 'transactionRequest')
        etree.SubElement(
            transaction_req,
            'transactionType').text = 'voidTransaction'
        etree.SubElement(
            transaction_req,
            'refTransId').text = self.transId

        print etree.tostring(root, pretty_print=True)
        return root

    # Void a transaction
    # TODO: Ask about CC settlement process
    @api.multi
    def void_payment(self):
        trans_recs = self.env['credit.card.transaction']

        for rec in self:
            if rec.state == 'posted' and rec.is_approved:

                # Preparing documents before sending request to Authorize.net
                self.cancel()

                trans_ids = trans_recs.search([('trans_id', '=', rec.transId)])
                trans_ids.write(
                    {'message': 'This transaction has been voided.'})

                req_xml_obj = rec._prepare_void_request()

                # Send the XML object to Authorize.net and return the XML
                # string
                res = self.env['credit.card.api']._send_request(req_xml_obj)

                # Get the transaction approval code
                approval_code = res.xpath('//responseCode')[0].text

                if approval_code == '1':
                    self.write({
                        'is_approved': False,
                        'transId': False,
                        'last_four': False
                    })

                # If the transaction is already voided on authorize.net but not the ERP,
                # walk through the same steps
                elif res.xpath('//transactionResponse/messages/message/code')[0].text == '310':
                    self.write({
                        'is_approved': False,
                        'transId': False,
                        'last_four': False
                    })

                # TODO: If the transaction is already settled, generate a
                # refund here

                # If something else went wrong, update the error text and do
                # nothing else
                else:
                    self._cr.rollback()
                    errordesc = res.xpath('//errorText')

                    # Auth.net may have sent an error message or a regular
                    # message
                    if errordesc:
                        errordesc = errordesc[0].text
                    else:
                        errordesc = res.xpath(
                            '//transactionResponse/messages/message/description')[0].text
                    raise Warning(errordesc)
        return False
