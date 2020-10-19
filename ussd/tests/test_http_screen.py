from unittest import mock, skip

import requests_mock

from ussd.tests import UssdTestCase


@skip("Hangs in CI. Needs to be fixed")
class TestHttpScreen(UssdTestCase.BaseUssdTestCase):
    validation_error_message = dict(
        screen_name="Screen not available",
        http_invalid_screen=dict(
            next_screen=['This field is required.'],
            session_key=['This field is required.'],
            http_request=['This field is required.']
        ),
        http_screen_invalid_method=dict(
            http_request=dict(
                method=['Must be one of: post, get, put, delete.'],
            )
        ),
        http_screen_invalid_synchronous=dict(
            synchronous=['Not a valid boolean.']
        )
    )

    def test(self):
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, json={"balance": 250})
            m.post(requests_mock.ANY, json={"balance": 250})
            ussd_client = self.ussd_client()

            self.assertEqual(
                "Testing response is being saved in "
                "session status code is 200 and "
                "balance is 250 and full content {'balance': 250}.\n",
                ussd_client.send('')
            )
            history = m.request_history
            assert history[0].method == 'GET'
            assert history[0].qs == {'phone_number': ['200'], 'session_id': [ussd_client.session_id]}
            assert not history[0].verify

            assert history[1].method == 'GET'

            assert history[2].method == 'POST'
            assert history[2].qs == {'phone_numbers': ['200', '201', '202'], 'session_id': [ussd_client.session_id]}
            assert history[2].verify

    @mock.patch("ussd.screens.http_screen.http_task.delay")
    def test_async_workflow(self, mock_http_task):
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, json={"balance": 250})
            m.post(requests_mock.ANY, json={"balance": 250})

            ussd_client = self.ussd_client()
            ussd_client.send('')

            # check http_task is called
            mock_http_task.assert_called_once_with(
                request_conf=dict(
                    method='get',
                    url="https://localhost:8000/mock/submission",
                    params={'phone_number': '200',
                            'session_id': ussd_client.session_id}
                )
            )

    def test_json_decoding(self):
        with requests_mock.Mocker() as m:
            m.get(requests_mock.ANY, text='Balance is 257')
            m.post(requests_mock.ANY, text='Balance is 257')

            ussd_client = self.ussd_client()
            ussd_client.send('')

            self.assertEqual(
                "Testing response is being saved in "
                "session status code is 200 and "
                "balance is  and full content Balance is 257.\n",
                ussd_client.send('')
            )
