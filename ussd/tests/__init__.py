import json
import logging
import os
import shutil
import tempfile
import uuid


from unittest import TestCase
from ussd.core import render_journey_as_graph, render_journey_as_mermaid_text, UssdEngine, UssdRequest, UssdResponse
from ussd.tests.sample_screen_definition import path
from ussd.store.journey_store.YamlJourneyStore import YamlJourneyStore
from ussd.session_store import SessionStore
from simplekv.fs import FilesystemStore


class UssdTestCase(object):
    """
    this contains two test that are required in each screen test case
    """

    class BaseUssdTestCase(TestCase):
        validate_ussd = True

        session_store = FilesystemStore("./session_data")

        def setUp(self):
            self.journey_store = YamlJourneyStore("sample_screen_definition", journey_directory='ussd/tests')
            file_prefix = self.__module__.split('.')[-1].replace('test_', '')
            self.journey_name = file_prefix
            journey_version_suffix = file_prefix + "_conf"

            self.valid_version = 'valid_' + journey_version_suffix
            self.invalid_version = 'invalid_' + journey_version_suffix

            self.mermaid_file = path + file_prefix + '/' + '/' + 'valid_' + file_prefix + '_mermaid.txt'
            self.graph_file = path + '/' + file_prefix + '/' + 'valid_' + file_prefix + '_graph.json'
            self.namespace = self.__module__.split('.')[-1]
            self.maxDiff = None

            super(UssdTestCase.BaseUssdTestCase, self).setUp()

            #
        #
        # @classmethod
        # def tearDownClass(cls) -> None:
        #     if os.path.exists('.journeys'):
        #         shutil.rmtree('.journeys')

        def _test_ussd_validation(self, version_to_validate, expected_validation,
                                  expected_errors):

            if self.validate_ussd:
                ussd_screens = self.journey_store.get(self.journey_name, version_to_validate)

                is_valid, error_message = UssdEngine.validate_ussd_journey(
                    ussd_screens)

                self.assertEqual(is_valid, expected_validation, error_message)

                for key, value in expected_errors.items():
                    args = (value, error_message[key], key)
                    if isinstance(value, dict):
                        self.assertDictEqual(*args)
                    else:
                        self.assertEqual(*args)

                self.assertDictEqual(error_message,
                                     expected_errors)

        def testing_valid_customer_journey(self):
            self._test_ussd_validation(self.valid_version, True, {})

        def testing_invalid_customer_journey(self):

            try:
                self._test_ussd_validation(self.invalid_version, False,
                                       getattr(self,
                                               "validation_error_message",
                                               {}))
            except Exception as e:
                if not (hasattr(self, "expected_error") and isinstance(e, self.__getattribute__("expected_error"))):
                    raise e

        def test_rendering_graph_js(self):
            if os.path.exists(self.graph_file):
                ussd_screens = self.journey_store.get(self.journey_name, self.valid_version)

                actual_graph_js = render_journey_as_graph(ussd_screens)

                expected_graph_js = json.loads(self.read_file_content(self.graph_file))

                for key, value in expected_graph_js["vertices"].items():
                    if value.get('id') == 'test_explicit_dict_loop':
                        for i in (
                                "a for apple\n",
                                "b for boy\n",
                                "c for cat\n"
                        ):
                            self.assertRegex(value.get('text'), i)
                    else:
                        self.assertDictEqual(value, actual_graph_js.vertices[key])
                # self.assertDictEqual(expected_graph_js["vertices"], actual_graph_js.vertices)

                for index, value in enumerate(expected_graph_js['edges']):
                    self.assertDictEqual(value, actual_graph_js.get_edges()[index])
                self.assertEqual(expected_graph_js["edges"], actual_graph_js.get_edges())

        def test_rendering_mermaid_js(self):
            if os.path.exists(self.mermaid_file):
                ussd_screens = self.journey_store.get(self.journey_name, self.valid_version)

                mermaid_text_format = render_journey_as_mermaid_text(ussd_screens)

                file_content = self.read_file_content(self.mermaid_file)

                expected_text_lines = file_content.split('\n')
                actual_text_lines = mermaid_text_format.split('\n')

                for index, line in enumerate(expected_text_lines):
                    self.assertEqual(line, actual_text_lines[index])

                self.assertEqual(mermaid_text_format, file_content)

        def read_file_content(self, file_path):
            with open(file_path) as f:
                mermaid_text = f.read()
            return mermaid_text

        def ussd_session(self, session_id):
            return SessionStore(session_id, kv_store=self.session_store)

        def ussd_client(self, generate_customer_journey=True, **kwargs):
            class UssdTestClient(object):
                def __init__(self, session_id=None, phone_number=200,
                             language='en', extra_payload=None, ):

                    if extra_payload is None:
                        extra_payload = {}
                    self.phone_number = phone_number
                    self.language = language
                    self.session_id = session_id \
                        if session_id is not None \
                        else str(uuid.uuid4())
                    self.extra_payload = extra_payload

                def send(self, ussd_input, raw=False):
                    payload = {
                        "session_id": self.session_id,
                        "ussd_input": ussd_input,
                        "phone_number": self.phone_number,
                        "language": self.language,
                    }
                    payload.update(self.extra_payload)

                    ussd_request = UssdRequest(**payload)

                    response = UssdEngine(ussd_request).ussd_dispatcher()

                    if raw:
                        return response
                    return str(response)

            customer_journey_conf = {
                'journey_name': self.journey_name,
                'journey_version': self.valid_version,
                "journey_store": self.journey_store
            }

            if kwargs.get('extra_payload'):
                customer_journey_conf.update(kwargs['extra_payload'])

            kwargs['extra_payload'] = customer_journey_conf

            return UssdTestClient(**kwargs)
