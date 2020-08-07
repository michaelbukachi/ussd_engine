from datetime import datetime

import staticconf
from flask.views import MethodView
from structlog import get_logger
from ussd import defaults, utilities
from ussd.core import MissingAttribute, UssdRequest, UssdResponse, _registered_ussd_handlers
from ussd.store.journey_store.YamlJourneyStore import load_yaml


class UssdView(MethodView):
    customer_journey_conf = None
    customer_journey_namespace = None

    def dispatch_request(self, *args, **kwargs):
        self.initial()
        res = super(UssdView, self).dispatch_request()
        res = self.finalize_response(res)
        return res

    def initial(self):
        self.ussd_initial()

    def ussd_initial(self, *args, **kwargs):
        if self.customer_journey_conf is None \
                or self.customer_journey_namespace is None:
            raise MissingAttribute("attribute customer_journey_conf and "
                                   "customer_journey_namespace are required")
        if self.customer_journey_namespace not in \
                staticconf.config.configuration_namespaces:
            load_yaml(
                self.customer_journey_conf
            )

        # confirm variable template has been loaded
        # get initial screen
        initial_screen = staticconf.read(
            "initial_screen",
            namespace=self.customer_journey_conf)

        if isinstance(initial_screen, dict) and \
                initial_screen.get('variables'):
            variable_conf = initial_screen['variables']
            file_path = variable_conf['file']
            namespace = variable_conf['namespace']
            if not namespace in \
                   staticconf.config.configuration_namespaces:
                load_yaml(file_path)

        self.initial_screen = initial_screen \
            if isinstance(initial_screen, dict) \
            else {"initial_screen": initial_screen}

    def finalize_response(self, response):
        if isinstance(response, UssdRequest):
            self.logger = get_logger(__name__).bind(**response.all_variables())
            try:
                ussd_response = self.ussd_dispatcher(response)
            except Exception as e:
                ussd_response = UssdResponse(str(e))
            return self.ussd_response_handler(ussd_response)
        return response

    def ussd_response_handler(self, ussd_response):
        return str(ussd_response)

    def ussd_dispatcher(self, ussd_request):

        # Clear input and initialize session if we are starting up
        if '_ussd_state' not in ussd_request.session:
            ussd_request.input = ''
            ussd_request.session['_ussd_state'] = {'next_screen': ''}
            ussd_request.session['ussd_interaction'] = []
            ussd_request.session['posted'] = False
            ussd_request.session['submit_data'] = {}
            ussd_request.session['session_id'] = ussd_request.session_id
            ussd_request.session['phone_number'] = ussd_request.phone_number

        # update ussd_request variable to session and template variables
        # to be used later for jinja2 evaluation
        ussd_request.session.update(ussd_request.all_variables())

        # for backward compatibility
        # there are some jinja template using ussd_request
        # eg. {{ussd_request.session_id}}
        ussd_request.session.update(
            {"ussd_request": ussd_request.all_variables()}
        )

        self.logger.debug('gateway_request', text=ussd_request.input)

        # Invoke handlers
        ussd_response = self.run_handlers(ussd_request)
        ussd_request.session[defaults.last_update] = \
            utilities.datetime_to_string(datetime.now())
        # Save session
        ussd_request.session.save()
        self.logger.debug('gateway_response', text=ussd_response.dumps(),
                          input="{redacted}")

        return ussd_response

    def run_handlers(self, ussd_request):

        handler = ussd_request.session['_ussd_state']['next_screen'] \
            if ussd_request.session.get('_ussd_state', {}).get('next_screen') \
            else "initial_screen"

        ussd_response = (ussd_request, handler)

        if handler != "initial_screen":
            # get start time
            start_time = utilities.string_to_datetime(
                ussd_request.session["ussd_interaction"][-1]["start_time"])
            end_time = datetime.now()
            # Report in milliseconds
            duration = (end_time - start_time).total_seconds() * 1000
            ussd_request.session["ussd_interaction"][-1].update(
                {
                    "input": ussd_request.input,
                    "end_time": utilities.datetime_to_string(end_time),
                    "duration": duration
                }
            )

        # Handle any forwarded Requests; loop until a Response is
        # eventually returned.
        while not isinstance(ussd_response, UssdResponse):
            ussd_request, handler = ussd_response

            screen_content = staticconf.read(
                handler,
                namespace=self.customer_journey_conf)

            screen_type = 'initial_screen' \
                if handler == "initial_screen" and \
                   isinstance(screen_content, str) \
                else screen_content['type']

            ussd_response = _registered_ussd_handlers[screen_type](
                ussd_request,
                handler,
                screen_content,
                initial_screen=self.initial_screen,
                logger=self.logger
            ).handle()

        ussd_request.session['_ussd_state']['next_screen'] = handler

        ussd_request.session['ussd_interaction'].append(
            {
                "screen_name": handler,
                "screen_text": str(ussd_response),
                "input": ussd_request.input,
                "start_time": utilities.datetime_to_string(datetime.now())
            }
        )
        # Attach session to outgoing response
        ussd_response.session = ussd_request.session

        return ussd_response
