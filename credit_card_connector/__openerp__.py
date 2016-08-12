{
    'name': 'Base module for Credit card processing',
    'version': '1.0',
    'description': """
Provides basic access for credit card payments.  Can enter card info directly or use
information on file to avoid entering CC information.
    """,
    'author': 'Sodexis, Inc',
    'website': 'http://www.sodexis.com',
    'depends': [
        'sale',
        'account',
        'account_cancel',
        'account_voucher',
        'rsa_encryption',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/create_customer_profile_view.xml',
        'wizard/create_payment_profile_view.xml',
        'views/creditcard_api_view.xml',
        'views/account_view.xml',
        'views/account_invoice_view.xml',
        'views/account_journal_view.xml',
        'views/account_payment_view.xml',
        'views/res_partner_view.xml',
    ],
}
