import time
from collections import OrderedDict
from datetime import datetime

from unittest import TestCase
from freezegun import freeze_time
from ussd import defaults as ussd_airflow_variables
from ussd.core import _registered_ussd_handlers, \
    UssdHandlerAbstract, MissingAttribute, \
    InvalidAttribute, UssdRequest, convert_error_response_to_mermaid_error
from ussd.tests import UssdTestCase
from ussd.utilities import datetime_to_string, string_to_datetime
from marshmallow import Schema, fields


class SampleSerializer(Schema):
    text = fields.Str(required=True)


class TestHandlerRegistration(TestCase):

    def test_happy_case(self):

        class TestOne(UssdHandlerAbstract):
            screen_type = "test_one"
            serializer = SampleSerializer

            def handle(self, req):
                pass

        self.assertTrue(_registered_ussd_handlers.get("test_one"))

        self.assertTrue(
            _registered_ussd_handlers['test_one'] == TestOne
        )

    @staticmethod
    def test_missing_screen_type_attribute():

        try:
            # missing screen_type
            class TestTwo(UssdHandlerAbstract):
                serializer = SampleSerializer

                def handle(self, req):
                    pass

            assert False, "should raise missing attriute name"
        except MissingAttribute:
            pass

    @staticmethod
    def test_missing_serializer_attribute():

        try:
            # missing validate schema
            class TestFour(UssdHandlerAbstract):
                screen_type = 'test_four'

            assert False, "should raise missing attriute name"
        except MissingAttribute:
            pass

    @staticmethod
    def test_invalid_serializer():

        try:
            # invalid serializer
            class TestFive(UssdHandlerAbstract):
                screen_type = 'test_five'
                serializer = "Sample serializer"

                def handle(self, req):
                    pass

            assert False, "should raise invalid serializer"
        except InvalidAttribute:
            pass


class TestUssdRequestCreation(TestCase):

    def test(self):
        session_id = '1234'
        ussd_request = UssdRequest('1234', '200', '', 'en',
                                   journey_name="sample_journey",
                                   journey_version="sample_customer_journey.yml"
                                   )

        self.assertTrue(len(session_id) < 8)

        self.assertTrue(len(ussd_request.session_id) >= 8)

        # test creating with session id as None
        self.assertRaises(InvalidAttribute,
                          UssdRequest,
                          None,
                          '200',
                          '',
                          'en',
                          journey_name="sample_journey",
                          journey_version="sample_customer_journey.yml"
                          )

        # session_id and using custom session_id can't been defined
        self.assertRaises(
            InvalidAttribute,
            UssdRequest,
            "sfewevae",
            "200",
            "",
            "en",
            use_built_in_session_management=True,
            journey_name = "sample_journey",
            journey_version = "sample_customer_journey.yml"
        )


class TestInheritance(UssdTestCase.BaseUssdTestCase):

    def get_client(self):
        return self.ussd_client(
            generate_customer_journey=False,
            extra_payload={
                'journey_name': "sample_journey",
                'journey_version': "sample_using_inheritance"

            }
        )

    def test(self):
        ussd_client = self.get_client()

        inherited_text = "Enter anything\n"

        # dial in
        self.assertEqual(
            inherited_text,
            ussd_client.send('')
        )

        # enter my first name
        self.assertEqual(
            inherited_text,
            ussd_client.send('Francis')
        )

        # enter second name
        self.assertEqual(
            "First input was Francis and second input was Mwangi\n"
            "1. Continue\n",
            ussd_client.send("Mwangi")
        )

    @freeze_time(datetime.now())
    def test_steps_recording(self):
        ussd_client = self.get_client()

        # dial in
        ussd_client.send('')

        # enter first name
        ussd_client.send('Francis')

        # enter second name
        ussd_client.send('Mwangi')

        # enter 1 to continue
        ussd_client.send('1')

        # press two to go back
        ussd_client.send('2')

        # enter 1 to continue
        ussd_client.send('1')

        # enter 1 to exit
        self.assertEqual(
            "This is the last screen",
            ussd_client.send('1')
        )

        now = datetime_to_string(datetime.now())
        expected_screen_interaction = [
            {
                "screen_name": "screen_one",
                "screen_text": "Enter anything\n",
                "input": "Francis",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_two",
                "screen_text": "Enter anything\n",
                "input": "Mwangi",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_three",
                "screen_text": "First input was Francis and "
                               "second input was Mwangi\n1. Continue\n",
                "input": "1",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_four",
                "screen_text": "Press 1 to exit or 2 to go back\n"
                               "1. Exit\n"
                               "2. Back\n",
                "input": "2",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_three",
                "screen_text": "First input was Francis and "
                               "second input was Mwangi\n1. Continue\n",
                "input": "1",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_four",
                "screen_text": "Press 1 to exit or 2 to go back\n"
                               "1. Exit\n"
                               "2. Back\n",
                "input": "1",
                "start_time": now,
                "end_time": now,
                "duration": 0.0
            },
            {
                "screen_name": "screen_five",
                "screen_text": "This is the last screen",
                "input": "",
                "start_time": now
            }

        ]

        session = self.ussd_session(ussd_client.session_id)

        self.assertEqual(
            session['ussd_interaction'],
            expected_screen_interaction
        )

    def testing_valid_customer_journey(self):
        self.journey_name = "sample_journey"
        self._test_ussd_validation(
            'sample_using_inheritance',
            True,
            {}
        )

    def testing_invalid_customer_journey(self):
        pass


class TestSessionManagement(UssdTestCase.BaseUssdTestCase):
    validate_ussd = False

    def get_client(self):
        return self.ussd_client(
            generate_customer_journey=False,
            extra_payload={
                "use_built_in_session_management": True,
                'journey_name': "sample_journey",
                'journey_version': "sample_used_for_testing_session_management",
                "session_id": None
            }
        )

    @staticmethod
    def _create_ussd_request(phone_number):
        return UssdRequest(None, phone_number, '', 'en',
                           use_built_in_session_management=True,
                           expiry=2, journey_name='sample_journey',
                           journey_version='sample_customer_journey.yml')

    def test_session_expiry(self):
        phone_number = 200
        req = self._create_ussd_request(phone_number)
        req.session['foo'] = 'bar'
        prev_items = req.session.items()
        req.session.save()

        # test a new session created within the time session data remains
        self.assertEqual(req.session['foo'],
                         self._create_ussd_request(phone_number).session['foo']
                         )
        time.sleep(2)

        # test after one second a session data has been cleared.
        new_req = self._create_ussd_request(phone_number)
        self.assertIsNone(new_req.session.get('foo'))
        # and previous data stored under another session id
        self.assertNotEqual(self.ussd_session(new_req.session[ussd_airflow_variables.previous_session_id]),
                            prev_items
                            )

    def test_session_expiry_using_inactivity(self):
        # Test session expiry is using last time session was updated
        phone_number = '201'
        req = self._create_ussd_request(phone_number)

        time.sleep(0.8)

        # confirm session_id hasn't changed
        self.assertEqual(
            req.session_id,
            self._create_ussd_request(phone_number).session_id
        )

        # make a change in session
        req = self._create_ussd_request(phone_number)
        req.session['name'] = 'mwas'
        req.session[ussd_airflow_variables.last_update] = datetime_to_string(
            datetime.now())
        req.session.save()

        time.sleep(0.8)

        # confirm even after the session was created 1.6 sec ago hasn't
        # been closed

        self.assertEqual(
            req.session['name'],
            self._create_ussd_request(phone_number).session['name']
        )

        time.sleep(3)

        # test now the session has been closed
        self.assertIsNone(
            self._create_ussd_request(phone_number).session.get('name')
        )

    def test_quit_screen_terminates_session(self):
        ussd_client = self.get_client()

        self.assertEqual(
            "Enter your name\n",
            ussd_client.send('')  # dial in
        )

        self.assertEqual(
            "Enter your age\n",
            ussd_client.send('Mwas')  # enter name
        )

        self.assertEqual(
            "You have entered your name as Mwas "
            "and your age as 24",
            ussd_client.send('24')
        )

        # dial in again to test the session has been closed
        self.assertEqual(
            "Enter your name\n",
            ussd_client.send('1')
        )

    def test_session_expiry_on_ussd(self):
        ussd_client = self.get_client()

        self.assertEqual(
            "Enter your name\n",
            ussd_client.send('')
        )

        # sleep for 1 sec for session to expiry
        time.sleep(1)

        self.assertEqual(
            "Enter your name\n",
            ussd_client.send('')
        )


class TestCommonFunctionality(TestCase):

    def test_date_time_conversion(self):
        now = datetime.now()
        now_str = datetime_to_string(now)

        self.assertEqual(now, string_to_datetime(now_str))

    def test_converting_error_response_to_mermaid_error(self):
        d = OrderedDict()
        d['e'] = ["e is required", "e is invalid"]

        b = OrderedDict()
        b['c'] = ['c is invalid']
        b['d'] = d

        error_response_sample = OrderedDict()
        error_response_sample['a'] = ["a is invalid"]
        error_response_sample['b'] = b
        error_response_sample['f'] = ['f is invalid']

        h = OrderedDict()
        h['h'] = ["This field is required."]
        error_response_sample['g'] = h

        unordered_dict = dict(
            a=["a is invalid"],
            b=dict(
                c=["c is invalid"],
                d=dict(
                    e=["e is required", "e is invalid"]
                )
            ),
            f=["f is invalid"],
            g=dict(h=["This field is required."])
        )

        self.assertEqual(error_response_sample, unordered_dict)

        mermaid_error_response = [
            {
                "path": ["a"],
                "message": "a is invalid",
            },
            {
                "path": ["b", "c"],
                "message": "c is invalid"
            },
            {
                "path": ["b", "d", "e"],
                "message": "e is required\ne is invalid"
            },
            {
                "path": ["f"],
                "message": "f is invalid"
            },
            {
                "path": ["g"],
                "message": "h is required."
            }
        ]

        actual_error = convert_error_response_to_mermaid_error(error_response_sample)

        for index, v in enumerate(mermaid_error_response):
            self.assertDictEqual(v, actual_error[index])
        self.assertListEqual(mermaid_error_response, actual_error)
