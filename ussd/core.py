"""
Comming soon
"""
import inspect
import json
import os
import re
import typing
from collections import namedtuple
from copy import copy
import datetime
from urllib.parse import unquote

import requests
from jinja2 import Environment
from structlog import get_logger

from ussd import defaults as ussd_airflow_variables
from ussd import utilities
from ussd.tasks import report_session
from .graph import Graph, Link, Vertex, convert_graph_to_mermaid_text
from ussd.screens.schema import UssdBaseScreenSchema
from ussd.store.journey_store import JourneyStore
from ussd.store.journey_store.YamlJourneyStore import YamlJourneyStore
from simplekv import KeyValueStore
from simplekv.fs import FilesystemStore
from ussd.session_store import SessionStore
from marshmallow.schema import SchemaMeta

_registered_ussd_handlers = {}
_registered_filters = {}
_customer_journey_files = []
_built_in_functions = {}

# initialize jinja2 environment
env = Environment(keep_trailing_newline=True)
env.filters.update(_registered_filters)


class MissingAttribute(Exception):
    pass


class InvalidAttribute(Exception):
    pass


class DuplicateSessionId(Exception):
    pass


def register_filter(func_name, *args, **kwargs):
    filter_name = func_name.__name__
    _registered_filters[filter_name] = func_name


def register_function(func_name, *args, **kwargs):
    function_name = func_name.__name__
    _built_in_functions[function_name] = func_name


class UssdRequest(object):
    """
    :param session_id:
        used to get session or create session if does not
        exits.

        If session is less than 8 we add *s* to make the session
        equal to 8

    :param phone_number:
        This the user identifier

    :param input:
        This ussd input the user has entered.

    :param language:
        Language to use to display ussd

    :param kwargs:
        Extra arguments.
        All the extra arguments will be set to the self attribute

        For instance:

        .. code-block:: python

            from ussd.core import UssdRequest

            ussdRequest = UssdRequest(
                '12345678', '702729654', '1', 'en',
                name='mwas'
            )

            # accessing kwarg argument
            ussdRequest.name
    """

    def __init__(self, session_id, phone_number,
                 ussd_input, language,
                 journey_name,
                 journey_store: JourneyStore = None,
                 journey_version=None,
                 session_store_backend: KeyValueStore = FilesystemStore("./session_data"),
                 default_language=None,
                 use_built_in_session_management=False,
                 expiry=180,
                 **kwargs):
        """
        :param session_id: Used to maintain session 
        :param phone_number: user dialing in   
        :param ussd_input: input entered by user
        :param language: language to be used
        :param default_language: language to used
        :param use_built_in_session_management: Used to enable ussd_airflow to 
            manage its own session, by default its set to False, is set to true 
        then the session_id should be None and expiry can't be None. 
        :param expiry: Its only used if use_built_in_session_management has
        been enabled. 
        :param kwargs: All other extra arguments
        """

        self.expiry = expiry
        # A bit of defensive programming to make sure
        # session_built_in_management has been initiated
        if use_built_in_session_management and session_id is not None:
            raise InvalidAttribute("When using built_in_session_management "
                                   "has been enabled session_id should "
                                   "be None")
        if use_built_in_session_management and expiry is None:
            raise InvalidAttribute("When built_in_session_management has been"
                                   "enabled expiry should not be None")
        # session id should not be None if built in session management
        # has not been enabled
        if session_id is None and not use_built_in_session_management:
            raise InvalidAttribute(
                "Session id should not be None if built in session management "
                "has not been enabled"
            )

        if session_id is None:
            session_id = str(phone_number)

        # for support when using django session table
        if len(str(session_id)) < 8:
            session_id = 's' * (8 - len(str(session_id))) + session_id

        self.phone_number = str(phone_number)
        self.input = unquote(ussd_input)
        self.language = language
        self.default_language = default_language or 'en'
        self.session_id = session_id

        # session store config
        self.use_built_in_session_management = use_built_in_session_management
        self.session_store_backend = session_store_backend
        self.session = self.get_session()
        self.session.set_expiry(self.expiry)

        # journey config
        if journey_store is None:
            self.journey_store = YamlJourneyStore("./ussd/tests/sample_screen_definition")
        else:
            self.journey_store = journey_store
        self.journey_name = journey_name
        self.journey_version = journey_version

        # screen configs
        self.menu_index_format = kwargs.get('menu_index_format', ". ")

        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)

    def forward(self, handler_name):
        """
        Forwards a copy of the current request to a new
        handler. Clears any input, as it is assumed this was meant for
        the previous handler. If you need to pass info between
        handlers, do it through the USSD session.
        """
        new_request = copy(self)
        new_request.input = ''
        return new_request, handler_name

    def all_variables(self):
        all_variables = copy(self.__dict__)

        # delete session if it exist
        all_variables.pop("session", None)

        return all_variables

    def built_in_session_management(self):
        if self.session_id is None:
            raise TypeError("Session id should not be null")

        session = self.get_session_from_store()

        # get last time session was updated
        if session.get_expiry_age() <= 0:
            # clear this session id
            # and save the data in another session key
            previous_session_key = session.cycle_data()
            session[ussd_airflow_variables.previous_session_id] = previous_session_key
        return session

    def get_session_from_store(self) -> SessionStore:
        return SessionStore(session_key=self.session_id,
                            kv_store=self.session_store_backend)

    def get_session(self) -> SessionStore:
        if self.use_built_in_session_management:
            return self.built_in_session_management()
        return self.get_session_from_store()

    def get_screens(self, screen_name=None):
        return self.journey_store.get(
            self.journey_name,
            self.journey_version,
            screen_name
        )


class UssdResponse(object):
    """
    :param text:
        This is the ussd text to display to the user
    :param status:
        This shows the status of ussd session.

        True -> to continue with the session

        False -> to end the session
    :param session:
        This is the session object of the ussd session
    """

    def __init__(self, text, status=True, session=None):
        self.text = text
        self.status = status
        self.session = session

    def dumps(self):
        return self.text

    def __str__(self):
        return self.dumps()


class UssdHandlerMetaClass(type):

    def __init__(cls, name, bases, attr, **kwargs):
        super(UssdHandlerMetaClass, cls).__init__(
            name, bases, attr)

        abstract = attr.get('abstract', False)

        if not abstract or attr.get('screen_type', '') == 'custom_screen':
            required_attributes = ('screen_type', 'serializer', 'handle')

            # check all attributes have been defined
            for attribute in required_attributes:
                if attribute not in attr and not hasattr(cls, attribute):
                    raise MissingAttribute(
                        "{0} is required in class {1}".format(
                            attribute, name)
                    )

            if not isinstance(attr['serializer'], SchemaMeta):
                raise InvalidAttribute(
                    "serializer should be a "
                    "instance of {serializer}".format(
                        serializer=SchemaMeta)
                )
            _registered_ussd_handlers[attr['screen_type']] = cls


class UssdHandlerAbstract(object, metaclass=UssdHandlerMetaClass):
    abstract = True

    def __init__(self, ussd_request: UssdRequest,
                 handler: str, screen_content: dict,
                 initial_screen: dict, logger=None,
                 raw_text=False):
        self.ussd_request = ussd_request
        self.handler = handler
        self.screen_content = screen_content
        self.raw_text = raw_text

        self.SINGLE_VAR = re.compile(r"^%s\s*(\w*)\s*%s$" % (
            '{{', '}}'))
        self.clean_regex = re.compile(r'^{{\s*(\S*)\s*}}$')
        self.logger = logger or get_logger(__name__).bind(
            handler=self.handler,
            screen_type=getattr(self, 'screen_type', 'custom_screen'),
            **self.ussd_request.all_variables(),
        )
        self.initial_screen = initial_screen

        self.pagination_config = self.initial_screen.get('pagination_config',
                                                         {})

        self.pagination_more_option = self._add_end_line(
            self.get_text(
                self.pagination_config.get('more_option', "more\n")
            )
        )
        self.pagination_back_option = self._add_end_line(
            self.get_text(
                self.pagination_config.get('back_option', "back\n")
            )
        )
        self.ussd_text_limit = self.pagination_config. \
            get("ussd_text_limit", ussd_airflow_variables.ussd_text_limit)

    def handle(self):
        if not self.ussd_request.input:
            ussd_response = self.show_ussd_content()
            return ussd_response if isinstance(ussd_response, UssdResponse) \
                else UssdResponse(str(ussd_response))
        return self.handle_ussd_input(self.ussd_request.input)

    def get_text_limit(self):
        return self.ussd_text_limit

    def show_ussd_content(self, **kwargs):
        raise NotImplementedError

    def handle_ussd_input(self, ussd_input):
        raise NotImplementedError

    def route_options(self, route_options=None):
        """
        iterates all the options executing expression comand.
        """
        if route_options is None:
            route_options = self.screen_content["next_screen"]

        if isinstance(route_options, str):
            return self.ussd_request.forward(route_options)

        loop_items = [0]
        if self.screen_content.get("with_items"):
            loop_items = self.evaluate_jija_expression(
                self.screen_content["with_items"],
                session=self.ussd_request.session
            ) or loop_items

        for item in loop_items:
            extra_context = {
                "item": item
            }
            if isinstance(loop_items, dict):
                extra_context.update(
                    dict(
                        key=item,
                        value=loop_items[item],
                        item={item: loop_items[item]}
                    )
                )

            for option in route_options:
                if self.evaluate_jija_expression(
                        option.get('expression') or option['condition'],
                        session=self.ussd_request.session,
                        extra_context=extra_context
                ):
                    return self.ussd_request.forward(option['next_screen'])
        return self.ussd_request.forward(
            self.screen_content['default_next_screen']
        )

    @staticmethod
    def get_session_items(session) -> dict:
        return dict(iter(session.items()))

    @classmethod
    def get_context(cls, session, extra_context=None):
        context = cls.get_session_items(session)

        context.update(
            dict(os.environ)
        )

        if extra_context is not None:
            context.update(extra_context)

        # add timestamp in the context
        context.update(
            dict(now=datetime.datetime.now(), datetime=datetime)
        )

        # add all built in functions
        context.update(
            _built_in_functions
        )
        return context

    @staticmethod
    def render_text(session, text, context=None, extra=None, encode=None):
        if context is None:
            context = UssdHandlerAbstract.get_context(
                session
            )

        if extra:
            context.update(extra)

        template = env.from_string(text or '')
        text = template.render(context)
        return json.dumps(text) if encode is 'json' else text

    def get_text(self, text_context=None):
        text_context = self.screen_content.get('text') \
            if text_context is None \
            else text_context

        if isinstance(text_context, dict):
            language = (self.ussd_request.session.get('override_language') or self.ussd_request.language) \
                if self.ussd_request.language \
                   in text_context.keys() \
                else self.ussd_request.default_language
            text_context = text_context[language]

        if self.raw_text:
            return text_context
        return self.render_text(
            self.ussd_request.session,
            text_context
        )

    @classmethod
    def evaluate_jija_expression(cls, expression, session,
                                 extra_context=None,
                                 lazy_evaluating=False,
                                 default=None):
        if not isinstance(expression, str) or \
                (lazy_evaluating and not cls._contains_vars(
                    expression)):
            return expression

        context = cls.get_context(
            session, extra_context=extra_context)

        try:
            expr = env.compile_expression(
                expression.replace("{{", "").replace("}}", "")
            )
            return expr(context)
        except Exception:
            try:
                return env.from_string(expression or '').render(context)
            except Exception:
                return default

    @classmethod
    def validate(cls, screen_name: str, ussd_content: dict) -> (bool, dict):
        screen_content = ussd_content[screen_name]
        schema = cls.serializer(context=ussd_content)
        errors = schema.validate(screen_content)
        return False if errors else True, errors

    @staticmethod
    def _contains_vars(data):
        '''
        returns True if the data contains a variable pattern
        '''
        if isinstance(data, str):
            for marker in ('{%', '{{', '{#'):
                if marker in data:
                    return True
        return False

    @staticmethod
    def _add_end_line(text):
        if text and '\n' not in text:
            text += '\n'
        return text

    def get_loop_items(self):
        loop_items = self.evaluate_jija_expression(
            self.screen_content["with_items"],
            session=self.ussd_request.session
        ) if self.screen_content.get("with_items") else [0] or [0]
        return loop_items

    @classmethod
    def render_request_conf(cls, session, data):
        if isinstance(data, str):
            jinja_results = cls.evaluate_jija_expression(data, session)
            return data if jinja_results is None else jinja_results

        elif isinstance(data, list):
            list_data = []
            for i in data:
                list_data.append(cls.render_request_conf(
                    session, i))

            return list_data

        elif isinstance(data, dict):
            dict_data = {}
            for key, value in data.items():
                dict_data.update(
                    {key: cls.render_request_conf(
                        session, value)}
                )
            return dict_data
        else:
            return data

    @staticmethod
    def get_variables_from_response_obj(response):
        response_varialbes = {}

        for i in inspect.getmembers(response):
            # Ignores anything starting with underscore
            # (that is, private and protected attributes)
            if not i[0].startswith('_'):
                # Ignores methods
                if not inspect.ismethod(i[1]) and \
                        type(i[1]) in \
                        (str, dict, int, dict, float, list, tuple):
                    if len(i) == 2:
                        response_varialbes.update(
                            {i[0]: i[1]}
                        )

        try:
            response_content = json.loads(response.content.decode())
        except json.JSONDecodeError:
            response_content = response.content.decode()

        if isinstance(response_content, dict):
            response_varialbes.update(
                response_content
            )

        # update content to save the one that has been decoded
        response_varialbes.update(
            {"content": response_content}
        )

        return response_varialbes

    @classmethod
    def make_request(cls, http_request_conf, response_session_key_save,
                     session, logger=None
                     ):
        logger = logger or get_logger(__name__).bind(
            action="make_request",
            session_id=session.session_key
        )
        logger.info("sending_request", **http_request_conf)
        response = requests.request(**http_request_conf)
        logger.info("response", status_code=response.status_code,
                    content=response.content)

        response_to_save = cls.get_variables_from_response_obj(response)

        # save response in session
        session[response_session_key_save] = response_to_save

        return response

    @staticmethod
    def fire_ussd_report_session_task(initial_screen: dict, session_id: str,
                                      support_countdown=True):
        ussd_report_session = initial_screen['ussd_report_session']
        args = (session_id,)
        kwargs = {'screen_content': initial_screen}
        keyword_args = ussd_report_session.get("async_parameters",
                                               {"countdown": 900}).copy()
        if not support_countdown and keyword_args.get('countdown'):
            del keyword_args['countdown']

        report_session.apply_async(
            args=args,
            kwargs=kwargs,
            **keyword_args
        )

    @staticmethod
    def get_handler(screen_type):
        return _registered_ussd_handlers[screen_type]

    def get_next_screens(self) -> typing.List[Link]:
        raise NotImplementedError

    def render_graph(self, ussd_journey: dict, graph: Graph):
        # adding the screen as vertex
        graph.add_vertex(Vertex(self.handler, self.show_ussd_content()))

        # get next screens
        next_screens = self.get_next_screens()

        # add links
        [graph.add_link(i) for i in next_screens]

        for i in next_screens:

            # check if node has been created
            if not (graph.get_vertex(i.end) and graph.get_vertex(i.end)['text'] != ""):
                graph.add_vertex(i.end)
                if ussd_journey.get(i.end.name):
                    next_screen_content = ussd_journey[i.end.name]
                    handler = self.get_handler(next_screen_content['type'])
                    handler(self.ussd_request, i.end.name, next_screen_content,
                            self.initial_screen, raw_text=self.raw_text). \
                        render_graph(ussd_journey, graph)


NextScreens = namedtuple("NextScreens", "next_screens links")


class UssdEngine(object):

    def __init__(self, ussd_request: UssdRequest):
        self.ussd_request = ussd_request
        initial_screen = ussd_request.get_screens('initial_screen')
        self.initial_screen = initial_screen \
            if isinstance(initial_screen, dict) \
            else {"initial_screen": initial_screen}
        self.logger = get_logger(__name__).bind(**ussd_request.all_variables())

    def ussd_dispatcher(self):

        # Clear input and initialize session if we are starting up
        if '_ussd_state' not in self.ussd_request.session:
            self.ussd_request.input = ''
            self.ussd_request.session['_ussd_state'] = {'next_screen': ''}
            self.ussd_request.session['ussd_interaction'] = []
            self.ussd_request.session['posted'] = False
            self.ussd_request.session['submit_data'] = {}
            self.ussd_request.session['session_id'] = self.ussd_request.session_id
            self.ussd_request.session['phone_number'] = self.ussd_request.phone_number

        # update self.ussd_request variable to session and template variables
        # to be used later for jinja2 evaluation
        self.ussd_request.session.update(self.ussd_request.all_variables())

        # for backward compatibility
        # there are some jinja template using ussd_request
        # eg. {{ussd_request.session_id}}
        self.ussd_request.session.update(
            {"ussd_request": self.ussd_request.all_variables()}
        )

        self.logger.debug('gateway_request', text=self.ussd_request.input)

        # Invoke handlers
        ussd_response = self.run_handlers()

        # Save session
        self.ussd_request.session.save()
        self.logger.debug('gateway_response', text=ussd_response.dumps(),
                          input="{redacted}")

        return ussd_response

    def run_handlers(self):

        handler = self.ussd_request.session['_ussd_state']['next_screen'] \
            if self.ussd_request.session.get('_ussd_state', {}).get('next_screen') \
            else "initial_screen"

        ussd_response = (self.ussd_request, handler)

        if handler != "initial_screen":
            # get start time
            start_time = utilities.string_to_datetime(
                self.ussd_request.session["ussd_interaction"][-1]["start_time"])
            end_time = datetime.datetime.now()
            # Report in milliseconds
            duration = (end_time - start_time).total_seconds() * 1000
            self.ussd_request.session["ussd_interaction"][-1].update(
                {
                    "input": self.ussd_request.input,
                    "end_time": utilities.datetime_to_string(end_time),
                    "duration": duration
                }
            )

        # Handle any forwarded Requests; loop until a Response is
        # eventually returned.
        while not isinstance(ussd_response, UssdResponse):
            self.ussd_request, handler = ussd_response

            screen_content = self.ussd_request.get_screens(handler)

            screen_type = 'initial_screen' \
                if handler == "initial_screen" and \
                   isinstance(screen_content, str) \
                else screen_content['type']

            ussd_response = _registered_ussd_handlers[screen_type](
                self.ussd_request,
                handler,
                screen_content,
                initial_screen=self.initial_screen,
                logger=self.logger
            ).handle()

        self.ussd_request.session['_ussd_state']['next_screen'] = handler

        self.ussd_request.session['ussd_interaction'].append(
            {
                "screen_name": handler,
                "screen_text": str(ussd_response),
                "input": self.ussd_request.input,
                "start_time": utilities.datetime_to_string(datetime.datetime.now())
            }
        )
        # Attach session to outgoing response
        ussd_response.session = self.ussd_request.session

        return ussd_response

    @staticmethod
    def validate_ussd_journey(ussd_content: dict) -> (bool, dict):
        errors = {}
        is_valid = True

        if not isinstance(ussd_content, dict):
            return False, {"_schema": ["journey should be a dictionary"]}

        # should define initial screen
        if not 'initial_screen' in ussd_content.keys():
            is_valid = False
            errors.update(
                {'hidden_fields': {
                    "initial_screen": ["This field is required."]
                }}
            )
        for screen_name, screen_content in ussd_content.items():
            # all screens should have type attribute
            if screen_name == "initial_screen" and \
                    isinstance(screen_content, str):
                if not screen_content in ussd_content.keys():
                    is_valid = False
                    errors.update(
                        dict(
                            screen_name="Screen not available"
                        )
                    )
                continue

            screen_type = screen_content.get('type')

            # all screen should have type field.
            base_schema = UssdBaseScreenSchema(context=ussd_content)
            base_errors = base_schema.validate(dict(type=screen_type))

            if base_errors:
                errors.update(
                    {screen_name: base_errors}
                )
                is_valid = False
                continue

            # all screen type have their handlers
            handlers = _registered_ussd_handlers[screen_type]

            screen_validation, screen_errors = handlers.validate(
                screen_name,
                ussd_content
            )
            if screen_errors:
                errors.update(
                    {screen_name: screen_errors}
                )

            if not screen_validation:
                is_valid = screen_validation

        return is_valid, errors

    @staticmethod
    def get_initial_screen(ussd_content: dict):
        initial_screen = ussd_content['initial_screen']
        return initial_screen if isinstance(initial_screen, dict) \
            else {"initial_screen": initial_screen}


def convert_error_response_to_mermaid_error(error_response: dict, errors=None, paths=None) -> list:
    errors = [] if errors is None else errors
    paths = [] if paths is None else paths

    for key, value in error_response.items():
        if isinstance(value, list):
            if len(value) == 1 and key == '_schema':
                    errors.append(
                        dict(path=paths, message=value[0])
                    )
            elif len(value) == 1 and value[0] == "This field is required.":
                errors.append(
                    dict(path=paths, message=value[0].replace('This field', key))
                )
            else:
                errors.append(
                    dict(path=paths + [key], message='\n'.join(value))
                )
        else:
            convert_error_response_to_mermaid_error(value, errors, paths=paths + [key])
    return errors


def _convert_obj_to_mermaid_error_obj(key, value, errors: list):
    if isinstance(value, list):
        return dict(path=[key], message='\n'.join(value))

    for k, v in value.items():
        error_obj = {}
        j = _convert_obj_to_mermaid_error_obj(k, v)
        error_obj['path'] = [key] + j['path']
        error_obj['message'] = j['message']
        errors.append(error_obj)

    return error_obj


def render_journey_as_graph(ussd_screen: dict) -> Graph:
    graph = Graph()

    initial_screen = ussd_screen['initial_screen']
    _registered_ussd_handlers['initial_screen'](
        UssdRequest("dummy", "dummy", "", "en",
                    journey_name="", journey_version=""),
        "initial_screen",
        initial_screen,
        initial_screen,
        raw_text=True
    ).render_graph(ussd_screen, graph)
    return graph


def render_journey_as_mermaid_text(ussd_screen: dict) -> str:
    return convert_graph_to_mermaid_text(
        render_journey_as_graph(ussd_screen)
    )
