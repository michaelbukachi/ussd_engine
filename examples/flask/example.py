import os

from flask import Flask, request
from simplekv.fs import FilesystemStore

from ussd.core import UssdRequest
from ussd.integrations.flask import UssdView
from ussd.store.journey_store.YamlJourneyStore import YamlJourneyStore

APP_DIR = os.path.dirname(os.path.realpath(__file__))
JOURNEYS_DIR = os.path.join(APP_DIR, ".journeys")
SESSION_DATA_DIR = os.path.join(APP_DIR, "session_data")


class UssdGateway(UssdView):
    customer_journey_conf = APP_DIR + "/journey.yml"
    customer_journey_namespace = "UssdGateway"

    def post(self):
        list_of_inputs = request.form["text"].split("*")
        text = (
            "*"
            if len(list_of_inputs) >= 2
               and list_of_inputs[-1] == ""
               and list_of_inputs[-2] == ""
            else list_of_inputs[-1]
        )

        phone = request.form["phoneNumber"].strip("+")
        session_id = request.form["sessionId"]
        if request.form.get("use_built_in_session_management", False):
            session_id = None

        name = None

        ussd_request = UssdRequest(
            phone_number=phone,
            session_id=session_id,
            ussd_input=text,
            journey_name=None,
            journey_store=YamlJourneyStore(journey_directory=JOURNEYS_DIR),
            session_store_backend=FilesystemStore(SESSION_DATA_DIR),
            service_code=request.form.get("serviceCode", ""),
            language=request.form.get("language", "en"),
            use_built_in_session_management=False,
        )
        return ussd_request

    def ussd_response_handler(self, ussd_response):
        if request.form.get("serviceCode") == "test":
            return super(UssdGateway, self).ussd_response_handler(ussd_response)
        if ussd_response.status:
            res = "CON" + " " + str(ussd_response)
            response = res
        else:
            res = "END" + " " + str(ussd_response)
            response = res
        return response


def create_app():
    app = Flask(__name__)
    app.add_url_rule('/ussd/', view_func=UssdGateway.as_view('ussd_view'))
    return app


if __name__ == '__main__':
    app = create_app()
    app.run()
