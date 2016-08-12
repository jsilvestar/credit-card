{
    'name': 'Authorize.Net API',
    'version': '1.0',
    'description': """
Provides Authorize.Net API access for credit card payments.  Can enter card info directly or use
information on file to avoid entering CC information.
    """,
    'author': 'Sodexis, Inc',
    'website': 'http://www.sodexis.com',
    'depends': [
        'credit_card_connector',
    ],
    'data': [
        'views/account_payment_view.xml',
        'views/creditcard_api_view.xml',
    ],
}
