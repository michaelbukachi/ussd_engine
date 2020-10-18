import os
import shutil
from unittest import TestCase
from ussd.store.journey_store import JourneyStoreApi
from unittest import mock
from copy import deepcopy
from marshmallow import ValidationError

b = 0


def helper(a, name="mwas"):
    global b
    b += 1


class BaseTestCase(TestCase):
    maxDiff = None

    journey = {
        "initial_screen": {
            "type": "initial_screen",
            "next_screen": "end_screen",
            "default_language": "en"
        },
        "end_screen": {
            "type": "quit_screen",
            "text": "end screen"
        }
    }

    driver_config = dict(
        journey_directory="./.journeys"
    )

    # @classmethod
    # def tearDownClass(cls) -> None:

    def tearDown(self) -> None:
        if os.path.exists('.journeys'):
            shutil.rmtree('.journeys')

    @staticmethod
    def _get_store_config_without_driver_name(store_config):
        # bad idea here but its only in tests
        # won't affect production performance
        new_store_config = deepcopy(store_config)

        if new_store_config.get("driver"):
            del new_store_config["driver"]
        return new_store_config

    @mock.patch("ussd.store.journey_store.JourneyStore.save")
    @mock.patch("ussd.store.journey_store.YamlJourneyStore.YamlJourneyStore.__init__")
    @mock.patch("ussd.store.journey_store.JourneyStoreApi._parameter_validation")
    def test_get_attribute(self, journey_store_parameter_validation, journey_store_init_mock, journey_store_save_mock):
        journey_store_parameter_validation.return_value = {}
        journey_store_init_mock.return_value = None

        JourneyStoreApi(driver_config=self.driver_config).save("test_save", self.journey, random_key_word="random_key_word")

        journey_store_parameter_validation.assert_called_once_with(
            journey_store_save_mock, "test_save", self.journey, random_key_word="random_key_word"
        )

        journey_store_init_mock.assert_called_once_with(
            **self._get_store_config_without_driver_name(self.driver_config),
        )

        journey_store_save_mock.assert_called_once_with(
            "test_save", self.journey, random_key_word="random_key_word"
        )

    def test_parameter_validation(self):

        # calling helper with only one argument
        self.assertDictEqual({}, JourneyStoreApi._parameter_validation(helper, a="a"))

        # call with a keyword
        # calling helper with only one argument and keyword
        self.assertDictEqual({}, JourneyStoreApi._parameter_validation(helper, "b", name="mwaside"))

        # calling with all keywords
        self.assertDictEqual({}, JourneyStoreApi._parameter_validation(helper, a="b", name="mwaside"))

        # calling with incorrect keyword
        self.assertDictEqual(
            dict(
                mwaside=["This field is not required"]
            ),
            JourneyStoreApi._parameter_validation(helper, "b", mwaside="mwaside")
        )

        # calling with incorrect arg
        self.assertDictEqual(
            dict(
                a=["This field is required"]
            ),
            JourneyStoreApi._parameter_validation(helper, name="mwaside")
        )

        # check it was not called
        helper('a')
        self.assertEqual(b, 1)

    def test_crud(self):
        store = JourneyStoreApi(driver_config=self.driver_config)

        name = "foo"
        version = "0.0.0"

        # save journey
        store.save(name=name, journey=self.journey, version=version)

        journey = store.get(name=name, version=version)
        self.assertEqual(self.journey, journey)

        store.delete(name=name)

        # confirm journey has been deleted
        self.assertRaises(ValidationError, store.get, name=name, version=version)

    def test_handle_action(self):

        store = JourneyStoreApi(driver_config=self.driver_config)

        name = "foo"
        version = "0.0.1"

        # save journey
        store.handle_action(action="save", name=name, journey=self.journey, version=version)

        # get journey that was created
        journey = store.handle_action(action="get", name=name, version=version)
        self.assertEqual(self.journey, journey)

        # create another journey
        journey2 = deepcopy(self.journey)
        journey2["end_screen"]["text"] = "journey 2"
        store.handle_action(action="save", name="bar", journey=journey2, version=version)
        # get journey that was created
        journey = store.handle_action(action="get", name="bar", version=version)
        self.assertEqual(journey2, journey)

        # now get all journeys
        journeys = store.handle_action(action="get")
        self.assertDictEqual({"foo": {version: self.journey}, "bar": {version: journey2}}, journeys)

        # delete journey that was created
        store.handle_action(action="delete", name=name)

        # confirm journey has been deleted
        self.assertRaises(ValidationError, store.get, name=name, version=version)

        # validate it action should be provided
        with self.assertRaises(ValidationError) as validation_err:
            # get journey without specifying the action
            store.handle_action(name=name, version=version)

        self.assertDictEqual(
            dict(
                action=["This field is required"]
            ),
            validation_err.exception.normalized_messages()
        )

        # test with invalid action
        with self.assertRaises(ValidationError) as validation_err:
            # get journey with invalid action
            store.handle_action(action="does_not_exist", name=name, version=version)

        self.assertDictEqual(
            dict(
                action=["action 'does_not_exist' is not allowed, only this methods are allowed; "
                        "save, delete, get, all, flush"]
            ),
            validation_err.exception.normalized_messages()
        )

    @mock.patch("ussd.store.journey_store.JourneyStoreApi._parameter_validation")
    @mock.patch("ussd.store.journey_store.JourneyStore.save")
    def test_post_alias_to_save(self, journey_store_save_mock, journey_store_parameter_validation):
        journey_store_parameter_validation.return_value = {}

        JourneyStoreApi(driver_config=self.driver_config).handle_action(action="post", name="test_save", journey=self.journey)

        journey_store_save_mock.assert_called_once_with(
            name="test_save", journey=self.journey
        )

    @mock.patch("ussd.store.journey_store.JourneyStoreApi._parameter_validation")
    @mock.patch("ussd.store.journey_store.JourneyStore.save")
    def test_put_alias_to_save(self, journey_store_save_mock, journey_store_parameter_validation):
        journey_store_parameter_validation.return_value = {}

        JourneyStoreApi(driver_config=self.driver_config).handle_action(action="put", name="test_save", journey=self.journey)

        journey_store_save_mock.assert_called_once_with(
            name="test_save", journey=self.journey
        )

