import json

import ddt
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings
import httpretty
import mock
from oscar.core.loading import get_model
from oscar.test import factories
from rest_framework import status

from ecommerce.extensions.api.serializers import RefundSerializer
from ecommerce.extensions.api.tests.test_authentication import AccessTokenMixin, OAUTH2_PROVIDER_URL
from ecommerce.extensions.api.v2.tests.views import JSON_CONTENT_TYPE
from ecommerce.extensions.refund.tests.factories import RefundLineFactory, RefundFactory
from ecommerce.extensions.refund.tests.mixins import RefundTestMixin
from ecommerce.tests.mixins import UserMixin, JwtMixin

Refund = get_model('refund', 'Refund')


class RefundCreateViewTests(RefundTestMixin, AccessTokenMixin, JwtMixin, UserMixin, TestCase):
    path = reverse('api:v2:refunds:create')

    def setUp(self):
        super(RefundCreateViewTests, self).setUp()
        self.course_id = 'edX/DemoX/Demo_Course'
        self.user = self.create_user()
        self.client.login(username=self.user.username, password=self.password)

    def assert_bad_request_response(self, response, detail):
        """ Assert the response has status code 406 and the appropriate detail message. """
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(response.content)
        self.assertEqual(data, {'detail': detail})

    def assert_ok_response(self, response):
        """ Assert the response has HTTP status 200 and no data. """
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), [])

    def _get_data(self, username=None, course_id=None):
        data = {}

        if username:
            data['username'] = username

        if course_id:
            data['course_id'] = course_id

        return json.dumps(data)

    def test_no_orders(self):
        """ If the user has no orders, no refund IDs should be returned. HTTP status should be 200. """
        self.assertFalse(self.user.orders.exists())
        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_ok_response(response)

    def test_missing_data(self):
        """
        If course_id is missing from the POST body, return HTTP 400
        """
        data = self._get_data(self.user.username)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_bad_request_response(response, 'No course_id specified.')

    def test_user_not_found(self):
        """
        If no user matching the username is found, return HTTP 400.
        """
        superuser = self.create_user(is_superuser=True)
        self.client.login(username=superuser.username, password=self.password)

        username = 'fakey-userson'
        data = self._get_data(username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_bad_request_response(response, 'User "{}" does not exist.'.format(username))

    def test_authentication_required(self):
        """ Clients MUST be authenticated. """
        self.client.logout()
        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_authentication(self):
        """ Client can authenticate with JWT. """
        self.client.logout()

        data = self._get_data(self.user.username, self.course_id)
        auth_header = 'JWT ' + self.generate_token({'username': self.user.username})

        response = self.client.post(self.path, data, JSON_CONTENT_TYPE, HTTP_AUTHORIZATION=auth_header)
        self.assert_ok_response(response)

    @httpretty.activate
    @override_settings(OAUTH2_PROVIDER_URL=OAUTH2_PROVIDER_URL)
    def test_oauth_authentication(self):
        """ Client can authenticate with OAuth. """
        self.client.logout()

        data = self._get_data(self.user.username, self.course_id)
        auth_header = 'Bearer ' + self.DEFAULT_TOKEN
        self._mock_access_token_response(username=self.user.username)

        response = self.client.post(self.path, data, JSON_CONTENT_TYPE, HTTP_AUTHORIZATION=auth_header)
        self.assert_ok_response(response)

    def test_session_authentication(self):
        """ Client can authenticate with a Django session. """
        self.client.logout()
        self.client.login(username=self.user.username, password=self.password)

        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_ok_response(response)

    def test_authorization(self):
        """ Client must be authenticated as the user matching the username field or a superuser. """

        # A normal user CANNOT create refunds for other users.
        self.client.login(username=self.user.username, password=self.password)
        data = self._get_data('not-me', self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # A superuser can create refunds for everyone.
        superuser = self.create_user(is_superuser=True)
        self.client.login(username=superuser.username, password=self.password)
        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_ok_response(response)

    def test_valid_order(self):
        """
        View should create a refund if an order/line are found eligible for refund.
        """
        order = self.create_order()
        self.assertFalse(Refund.objects.exists())
        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        refund = Refund.objects.latest()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(json.loads(response.content), [refund.id])
        self.assert_refund_matches_order(refund, order)

        # A second call should result in no additional refunds being created
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_ok_response(response)

    def test_refunded_line(self):
        """
        View should NOT create a refund if an order/line is found, and has an existing refund.
        """
        order = self.create_order()
        Refund.objects.all().delete()
        RefundLineFactory(order_line=order.lines.first())
        self.assertEqual(Refund.objects.count(), 1)

        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)
        self.assert_ok_response(response)
        self.assertEqual(Refund.objects.count(), 1)

    def test_non_course_order(self):
        """ Refunds should NOT be created for orders with no line items related to courses. """
        Refund.objects.all().delete()
        factories.create_order(user=self.user)
        self.assertEqual(Refund.objects.count(), 0)

        data = self._get_data(self.user.username, self.course_id)
        response = self.client.post(self.path, data, JSON_CONTENT_TYPE)

        self.assert_ok_response(response)
        self.assertEqual(Refund.objects.count(), 0)


@ddt.ddt
class RefundProcessViewTests(UserMixin, TestCase):
    def setUp(self):
        super(RefundProcessViewTests, self).setUp()

        self.user = self.create_user(is_staff=True)
        self.client.login(username=self.user.username, password=self.password)
        self.refund = RefundFactory(user=self.user)

    def put(self, action):
        data = '{{"action": "{}"}}'.format(action)
        path = reverse('api:v2:refunds:process', kwargs={'pk': self.refund.id})
        return self.client.put(path, data, JSON_CONTENT_TYPE)

    def test_staff_only(self):
        """ The view should only be accessible to staff users. """
        user = self.create_user(is_staff=False)
        self.client.login(username=user.username, password=self.password)
        response = self.put('approve')
        self.assertEqual(response.status_code, 403)

    def test_invalid_action(self):
        """ If the action is neither approve nor deny, the view should return HTTP 400. """
        response = self.put('reject')
        self.assertEqual(response.status_code, 400)

    @ddt.data('approve', 'deny')
    def test_success(self, action):
        """ If the action succeeds, the view should return HTTP 200 and the serialized Refund. """
        with mock.patch('ecommerce.extensions.refund.models.Refund.{}'.format(action), mock.Mock(return_value=True)):
            response = self.put(action)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, RefundSerializer(self.refund).data)

    @ddt.data('approve', 'deny')
    def test_failure(self, action):
        """ If the action fails, the view should return HTTP 500 and the serialized Refund. """
        with mock.patch('ecommerce.extensions.refund.models.Refund.{}'.format(action), mock.Mock(return_value=False)):
            response = self.put(action)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.data, RefundSerializer(self.refund).data)