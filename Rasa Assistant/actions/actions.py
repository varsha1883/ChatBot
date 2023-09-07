import logging
from typing import Dict, Text, Any, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher, Action
from rasa_sdk.forms import FormAction, FormValidationAction
from rasa_sdk.events import AllSlotsReset, SlotSet, UserUtteranceReverted, ConversationPaused
from actions.snow import SnowAPI
import random
import requests
import os
import email, smtplib, ssl
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)
vers = "vers: 0.1.0, date: Apr 2, 2020"
logger.debug(vers)

snow = SnowAPI()
localmode = snow.localmode
logger.debug(f"Local mode: {snow.localmode}")


class ActionAskEmail(Action):
    def name(self) -> Text:
        return "action_ask_email"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        if tracker.get_slot("previous_email"):
            dispatcher.utter_message(template=f"utter_ask_use_previous_email", )
        else:
            dispatcher.utter_message(template=f"utter_ask_email")
        return []


def _validate_email(
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
) -> Dict[Text, Any]:
    """Validate email is in ticket system."""
    if not value:
        return {"email": None, "previous_email": None}
    elif isinstance(value, bool):
        value = tracker.get_slot("previous_email")

    if localmode:
        return {"email": value}

    results = snow.email_to_sysid(value)
    caller_id = results.get("caller_id")

    if caller_id:
        return {"email": value, "caller_id": caller_id}
    elif isinstance(caller_id, list):
        dispatcher.utter_message(template="utter_no_email")
        return {"email": None}
    else:
        dispatcher.utter_message(results.get("error"))
        return {"email": None}


class ValidateOpenIncidentForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_open_incident_form"

    def validate_email(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate email is in ticket system."""
        return _validate_email(value, dispatcher, tracker, domain)

    def validate_priority(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate priority is a valid value."""

        if value.lower() in snow.priority_db():
            return {"priority": value}
        else:
            dispatcher.utter_message(template="utter_no_priority")
            return {"priority": None}


class ActionOpenIncident(Action):
    def name(self) -> Text:
        return "action_open_incident"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Create an incident and return details or
        if localmode return incident details as if incident
        was created
        """

        priority = tracker.get_slot("priority")
        email = tracker.get_slot("email")
        problem_description = tracker.get_slot("problem_description")
        incident_title = tracker.get_slot("incident_title")
        confirm = tracker.get_slot("confirm")
        if not confirm:
            dispatcher.utter_message(
                template="utter_incident_creation_canceled"
            )
            return [AllSlotsReset(), SlotSet("previous_email", email)]

        if localmode:
            message = (
                f"An incident with the following details would be opened "
                f"if ServiceNow was connected:\n"
                f"email: {email}\n"
                f"problem description: {problem_description}\n"
                f"title: {incident_title}\n"
                f"priority: {priority}"
            )
        else:
            snow_priority = snow.priority_db().get(priority)
            response = snow.create_incident(
                description=problem_description,
                short_description=incident_title,
                priority=snow_priority,
                email=email,
            )
            incident_number = (
                response.get("content", {}).get("result", {}).get("number")
            )
            if incident_number:
                message = (
                    f"Successfully opened up incident {incident_number} "
                    f"for you. Someone will reach out soon."
                )
            else:
                message = (
                    f"Something went wrong while opening an incident for you. "
                    f"{response.get('error')}"
                )
        dispatcher.utter_message(message)
        return [AllSlotsReset(), SlotSet("previous_email", email)]


class ActionOpenRequest(Action):
    def name(self) -> Text:
        return "action_open_request"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Create an incident and return details or
        if localmode return incident details as if incident
        was created
        """

        email = tracker.get_slot("email")
        description = tracker.get_slot("description")
        request_title = tracker.get_slot("request_title")
        priority = tracker.get_slot("priority")
        confirm = tracker.get_slot("request_confirm")
        if not confirm:
            dispatcher.utter_message(
                template="utter_incident_creation_canceled"
            )
            return [AllSlotsReset(), SlotSet("previous_email", email)]

        if localmode:
            message = (
                f"An incident with the following details would be opened "
                f"if ServiceNow was connected:\n"
                f"email: {email}\n"
                f"problem description: {description}\n"
                f"title: {request_title}\n"
                f"priority: {priority}"
            )
        else:
            snow_priority = snow.priority_db().get(priority)
            response = snow.create_request(
                description=description,
                short_description=request_title,
                priority=snow_priority,
                email=email,
            )
            request_number = (
                response.get("content", {}).get("result", {}).get("number")
            )
            if request_number:
                message = (
                    f"Successfully submitted the request {request_number} "
                    f"for you. Someone will reach out soon."
                )
            else:
                message = (
                    f"Something went wrong while submitting a request for you. "
                    f"{response.get('error')}"
                )
        dispatcher.utter_message(message)
        return [AllSlotsReset(), SlotSet("previous_email", email)]


class IncidentStatusForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_incident_status_form"

    def validate_email(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validate email is in ticket system."""
        return _validate_email(value, dispatcher, tracker, domain)


class ActionCheckIncidentStatus(Action):
    def name(self) -> Text:
        return "action_check_incident_status"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Look up all incidents associated with email address
           and return status of each"""

        email = tracker.get_slot("email")

        incident_states = {
            "New": "is currently awaiting triage",
            "In Progress": "is currently in progress",
            "On Hold": "has been put on hold",
            "Closed": "has been closed",
        }
        if localmode:
            status = random.choice(list(incident_states.values()))
            message = (
                f"Since ServiceNow isn't connected, I'm making this up!\n"
                f"The most recent incident for {email} {status}"
            )
        else:
            incidents_result = snow.retrieve_incidents(email)
            incidents = incidents_result.get("incidents")
            if incidents:
                message = "\n".join(
                    [
                        f'Incident {i.get("number")}: '
                        f'"{i.get("short_description")}", '
                        f'opened on {i.get("opened_at")} '
                        f'{incident_states.get(i.get("incident_state"))}'
                        for i in incidents
                    ]
                )

            else:
                message = f"{incidents_result.get('error')}"

        dispatcher.utter_message(message)
        return [AllSlotsReset(), SlotSet("previous_email", email)]


class total_active_incidents(Action):
    def name(self) -> Text:
        return "action_check_incident_status"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Look up all incidents associated with email address
           and return status of each"""

        email = tracker.get_slot("email")
        df = snow.getdf(email)
        x = snow.getactive(df)
        return x[0]


class ActionSubmit(Action):
    def name(self) -> Text:
        return "action_submit"

    def run(
            self,
            dispatcher,
            tracker: Tracker,
            domain: "DomainDict",
    ) -> List[Dict[Text, Any]]:
        SendEmail(
            tracker.get_slot("email"),
            tracker.get_slot("subject"),
            tracker.get_slot("message")
        )
        dispatcher.utter_message(
            "Thanks for providing the details. We have sent you a mail at {}".format(tracker.get_slot("email")))
        return []


def SendEmail(toaddr, subject, message):
    fromaddr = "rasachatbot140@gmail.com"
    # password = "Password@123"
    password = input("Type your password and press enter: ")
    # instance of MIMEMultipart
    msg = MIMEMultipart()

    # storing the senders email address
    msg['From'] = fromaddr

    # storing the receivers email address
    msg['To'] = toaddr

    # storing the subject
    msg['Subject'] = subject

    # string to store the body of the mail
    body = message

    # attach the body with the msg instance
    msg.attach(MIMEText(body, 'plain'))

    # open the file to be sent
    # filename = "/home/ashish/Downloads/webinar_rasa2_0.png"
    # attachment = open(filename, "rb")
    #
    # # instance of MIMEBase and named as p
    # p = MIMEBase('application', 'octet-stream')
    #
    # # To change the payload into encoded form
    # p.set_payload((attachment).read())
    #
    # # encode into base64
    # encoders.encode_base64(p)
    #
    # p.add_header('Content-Disposition', "attachment; filename= %s" % filename)
    #
    # # attach the instance 'p' to instance 'msg'
    # msg.attach(p)

    # creates SMTP session
    s = smtplib.SMTP('smtp.gmail.com', 587)

    # start TLS for security
    s.starttls()

    # Authentication
    try:
        s.login(fromaddr, password)

        # Converts the Multipart msg into a string
        text = msg.as_string()

        # sending the mail
        s.sendmail(fromaddr, toaddr, text)
    except:
        print("An Error occured while sending email.")
    finally:
        # terminating the session
        s.quit()

# class ActionHelloWorld(Action):
#
#     def name(self) -> Text:
#         return "action_hello_world"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         dispatcher.utter_message(text="Hello World!")
#
#         return []
