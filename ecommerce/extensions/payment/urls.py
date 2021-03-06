from django.conf import settings
from django.conf.urls import include, url

from ecommerce.extensions.payment.views import PaymentFailedView, SDNFailure, cybersource, paypal, stripe

CYBERSOURCE_APPLE_PAY_URLS = [
    url(r'^authorize/$', cybersource.CybersourceApplePayAuthorizationView.as_view(), name='authorize'),
    url(r'^start-session/$', cybersource.ApplePayStartSessionView.as_view(), name='start_session'),
]
CYBERSOURCE_URLS = [
    url(r'^apple-pay/', include(CYBERSOURCE_APPLE_PAY_URLS, namespace='apple_pay')),
    url(r'^redirect/$', cybersource.CybersourceInterstitialView.as_view(), name='redirect'),
    url(r'^submit/$', cybersource.CybersourceSubmitView.as_view(), name='submit'),
]

PAYPAL_URLS = [
    url(r'^execute/$', paypal.PaypalPaymentExecutionView.as_view(), name='execute'),
    url(r'^profiles/$', paypal.PaypalProfileAdminView.as_view(), name='profiles'),
]

SDN_URLS = [
    url(r'^failure/$', SDNFailure.as_view(), name='failure'),
]

STRIPE_URLS = [
    url(r'^submit/$', stripe.StripeSubmitView.as_view(), name='submit'),
]



urlpatterns = [
    url(r'^cybersource/', include(CYBERSOURCE_URLS, namespace='cybersource')),
    url(r'^error/$', PaymentFailedView.as_view(), name='payment_error'),
    url(r'^paypal/', include(PAYPAL_URLS, namespace='paypal')),
    url(r'^sdn/', include(SDN_URLS, namespace='sdn')),
    url(r'^stripe/', include(STRIPE_URLS, namespace='stripe')),
]

if settings.ENABLE_ALIPAY_WECHATPAY:
    from ecommerce.extensions.payment.views import alipay, wechatpay
    ALIPAY_URLS = [
        url(r'^execute/$', alipay.AlipayPaymentExecutionView.as_view(), name='execute'),
        url(r'^result/$', alipay.AlipayPaymentResultView.as_view(), name='result'),
    ]
    WECHATPAY_URLS = [
        url(r'^order_query/(?P<pk>\d+)$', wechatpay.WechatpayOrderQuery.as_view(), name='order_query'),
        url(r'^execute/$', wechatpay.WechatpayPaymentExecutionView.as_view(), name='execute'),
    ]
    urlpatterns.append(url(r'^alipay/', include(ALIPAY_URLS, namespace='alipay')))
    urlpatterns.append(url(r'^wechatpay/', include(WECHATPAY_URLS, namespace='wechatpay')))
