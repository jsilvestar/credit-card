{
    'name': 'Braintree API',
    'version': '1.0',
    'description': """
Provides Braintree API access for credit card payments.  Can enter card info directly or use
information on file to avoid entering CC information.
    """,
    'author': 'Sodexis, Inc',
    'website': 'http://www.sodexis.com',
    'depends': [
        'credit_card_connector',
        'website',
    ],
    'data': [
        'wizard/create_payment_profile_view.xml',
        'views/account_payment_view.xml',
        'views/account_invoice_view.xml',
        'views/sale_view.xml',
        'views/res_partner_view.xml',
        'views/template.xml',
    ],
}
