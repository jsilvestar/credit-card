import logging
_logger = logging.getLogger(__name__)
from braintree import Transaction

from openerp import models, fields, api, _
from openerp.exceptions import UserError, except_orm, Warning

ENCRYPTED_FIELDS = ['cc_number', 'cc_cvv', 'cc_exp_month', 'cc_exp_year']


class account_payment(models.Model):
    _inherit = 'account.payment'

    # Prepare a dict request to send validating the transaction
    @api.model
    def _prepare_transaction_request(self):
        token = self.cim_payment_id.payprofile_id
        return {
            "payment_method_token": token,
            "amount": str(self.amount),
            "order_id": str(self.id),
            "options": {
                "submit_for_settlement": True,
            }
        }

    @api.multi
    def post(self):
        trans_vals = {}
        payment_vals = {}

        # Process the valid id list
        res = super(account_payment, self).post()

        for payment in self:
            # Make sure there's an amount, $0 payments are worthless!
            if not payment.amount:
                raise UserError(
                    '_(Paid Amount is $0, please enter a payment amount.)')

            if payment.new_card:
                if not (payment.cc_number and payment.cc_exp_month and payment.cc_exp_year):
                    raise UserError(
                        _('Provide credit card details for Transaction'))
            if payment.use_cc:
                if not payment.cim_payment_id and not payment.new_card:
                    raise UserError(
                        _('Select or create a Payment profile'))
                # When 'Always create profile' boolean field is selected at
                # API credential configuration, the customer profile and
                # payment profile is created before sending info to
                # braintree
                search_ids = self.env['credit.card.api'].search(
                    [('create_profile', '=', True)])
                if search_ids:
                    if not payment.cim_id:
                        payment.create_customer_profile()
                    if payment.new_card:
                        payment.create_payment_profile()

            # If this is a CC payment, authenticate with braintree
            if payment.use_cc:
                # Prepare documents required for transaction processing
                self.last_four = payment.cim_payment_id.last_four
                # Transaction object record is created here
                invoice_id = payment.invoice_ids.id
                trans_vals = {
                    'cim_id': payment.cim_id.id,
                    'pim_id': payment.cim_payment_id.id,
                    'amount': payment.amount,
                    'invoice_id': invoice_id,
                    'payment_id': payment.id
                }
                transaction_rec = self.env[
                    'credit.card.transaction'].create(trans_vals)

                # Configure braintree environment
                self.env['credit.card.api']._configure_environment()

                # Prepare the XML request
                req_dict_obj = payment._prepare_transaction_request()

                # Send request to braintree
                result = Transaction.sale(req_dict_obj)

                if result.is_success:
                    pass
                else:
                    message = result.message
                    if result.transaction:
                        message = "Code - %s\n%s" % (
                            result.transaction.processor_response_code,
                            result.transaction.processor_response_text)
                    # Rollback cursor and store card decline reason
                    self._cr.rollback()
                    payment.invoice_ids.write(
                        {'card_declined_note': message, 'card_declined': True})
                    self._cr.commit()
                    raise Warning(message)

                # Parsing will vary depending on if it's a card on file or
                # one-time card
                if payment.cim_payment_id:
                    approval_code = result.transaction.status
                    transId = result.transaction.id
                    errordesc = result.transaction.processor_response_text
                    errorid = result.transaction.processor_response_code
                    card_type = result.transaction.credit_card.get('card_type')
                    authCode = result.transaction.processor_authorization_code
                    avsResultCode = result.transaction.avs_street_address_response_code
                    cvvResultCode = result.transaction.cvv_response_code

                CARD_CODE_RESPONSE = {
                    'M': 'Match',
                    'N': 'Does not match',
                    'P': 'Not Processed',
                    'S': 'Issuer does not participate',
                    'I': 'CVV not provided',
                }
                AVS_RESPONSE = {
                    'A': 'Address (Street) matches, ZIP does not',
                    'B': 'Address information not provided for AVS check',
                    'E': 'AVS error',
                    'G': 'Non-U.S. Card Issuing Bank',
                    'I': 'Street Address not provided',
                    'M': 'Street/Postal code matches',
                    'N': 'No Match on Address (Street) or ZIP',
                    'P': 'AVS not applicable for this transaction',
                    'R': 'Retry-System unavailable or timed out',
                    'S': 'Service not supported by issuer',
                    'U': 'Address information is unavailable',
                    'W': 'Nine digit ZIP matches, Address (Street) does not',
                    'X': 'Address (Street) and nine digit ZIP match',
                    'Y': 'Address (Street) and five digit ZIP maetch',
                    'Z': 'Five digit ZIP matches, Address (Street) does not',
                }
                if cvvResultCode in ['M', 'N', 'P', 'S', 'I']:
                    cvvResultCode = CARD_CODE_RESPONSE[cvvResultCode]
                if avsResultCode in ['A', 'B', 'E', 'G', 'I', 'M', 'N', 'P', 'R', 'S', 'U', 'W', 'X', 'Y', 'Z']:
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
                payment_vals['is_approved'] = True
                payment_vals['transId'] = transId
                payment.write(payment_vals)
                transaction_rec.write(trans_vals)
                payment.invoice_ids.write(
                    {'card_declined_note': '', 'card_declined': False})
        return res

    # Void a transaction
    @api.multi
    def void_payment(self):
        for payment in self:
            if payment.state == 'posted' and payment.is_approved:

                # Preparing documents before sending request to braintree
                payment.cancel()

                trans_ids = self.env['credit.card.transaction'].search(
                    [('trans_id', '=', payment.transId)])
                trans_ids.write(
                    {'message': _('This transaction has been voided.')})

                # Configure braintree environment
                self.env['credit.card.api']._configure_environment()

                result = Transaction.void(payment.transId)

                if not result.is_success:
                    raise Warning(result.message)

        return True
