from ussd.core import UssdHandlerAbstract
from ussd.screens.schema import UssdBaseScreenSchema, NextUssdScreenSchema, PaginationConfigSchema
from ussd.graph import Vertex, Link
import typing
from marshmallow import Schema, fields, validate


class VariableDefinitionSchema(Schema):
    file = fields.Str(required=True)
    namespace = fields.Str(required=True)


class ValidateResponseSerializerSchema(Schema):
    expression = fields.Str()


class RetryMechanismSchema(Schema):
    max_retries = fields.Integer(required=True)


class UssdReportSessionSchema(Schema):
    session_key = fields.Str(validate=validate.Length(max=100), required=True)
    validate_response = fields.List(fields.Nested(ValidateResponseSerializerSchema), required=True)
    request_conf = fields.Dict(required=True)
    retry_mechanism = fields.Nested(RetryMechanismSchema, required=False)
    async_parameters = fields.Dict(required=False)


class InitialScreenSchema(UssdBaseScreenSchema, NextUssdScreenSchema):
    variables = fields.Nested(VariableDefinitionSchema, required=False)
    create_ussd_variables = fields.Dict(default={}, required=False)
    default_language = fields.Str(required=False, default="en")
    ussd_report_session = fields.Nested(UssdReportSessionSchema, required=False)
    pagination_config = fields.Nested(PaginationConfigSchema, required=False)


class InitialScreen(UssdHandlerAbstract):
    """This screen is mandatory in any customer journey.
    It is the screen all new ussd session go to.

    example of one

        .. code-block:: yaml

            initial_screen: enter_height

            first_screen:
            type: quit
            text: This is the first screen

    Its is also used to define variable file if you have one.
    Example when defining variable file

        .. code-block:: yaml

            initial_screen:
                screen: screen_one
                variables:
                    file: /path/of/your/variable/file.yml
                    namespace: used_to_save_the_variable
    Sometimes you want to send ussd session to some 3rd party application when
    the session has been terminated.
    
    We can easily do that at end of session i.e quit screen, But for those
    scenarios where session is terminated by user or mno we don't know that 
    unless the mno send us a request. 
    
    Most mnos don't send notifier 3rd party application about the session being
    dropped. The work around we use is schedule celery task to run after 
    15 minutes ( by that time we know there is no active session)
    
    Below is an example of how to schedule a ussd report session after 15min
        
    
    example:
        
        .. code-block:: yaml
        
            initial_screen:
                type: initial_screen
                next_screen: screen_one
                ussd_report_session:
                    session_key: reported
                    retry_mechanism:
                        max_retries: 3
                    validate_response:
                        - expression: "{{reported.status_code}} == 200"
                    request_conf:
                        url: localhost:8006/api
                        method: post
                        data:
                            ussd_interaction: "{{ussd_interaction}}"
                            session_id: "{{session_id}}"
                    async_parameters:
                        queue: report_session
                        countdown: 900
                    
        
        Lets explain the variables in ussd_report_session
            - session_key ( Mandatory )
                response of ussd report session would be saved under that key
                in session store
                
            - request_conf ( Mandatory )
                Those are the parameters to be used to make request to 
                report ussd session
            
            - validate_response ( Mandatory )
                After making ussd report request the framework will evaluate 
                your options and if one of them is valid it would 
                mark session as posted (This is used to avoid double ussd 
                submission)
                
            - retry_mechanism ( Optional )
                After validating your response and all of them fail 
                we will go ahead and retry if this field is active. 
                
            - async_parameters ( Optional )
                This is are the parameters used to make ussd request
            
            
                
    """
    screen_type = "initial_screen"

    serializer = InitialScreenSchema

    def get_next_screens(self) -> typing.List[Link]:
        next_screens = self.screen_content['next_screen']
        return [Link(Vertex(self.handler), Vertex(next_screens, ''), "")]

    def show_ussd_content(self):
        return ""

    def handle(self):

        if isinstance(self.screen_content, dict):

            # create ussd variables defined int the yaml
            self.create_variables()

            # set default language
            self.set_language()

            next_screen = self.screen_content['next_screen']

            # call report session
            if self.screen_content.get('ussd_report_session'):
                self.fire_ussd_report_session_task(self.initial_screen,
                                                   self.ussd_request.session_id
                                                   )
        else:
            next_screen = self.screen_content
        return self.route_options(route_options=next_screen)

    def create_variables(self):
        for key, value in \
                self.screen_content.get('create_ussd_variables', {}). \
                        items():
            self.ussd_request.session[key] = \
                self.evaluate_jija_expression(value,
                                              lazy_evaluating=True,
                                              session=self.ussd_request.session
                                              )

    def set_language(self):
        self.ussd_request.session['default_language'] = \
            self.screen_content.get('default_language', 'en')
