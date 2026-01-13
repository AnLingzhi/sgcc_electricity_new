import json
import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
from sympy import true
import paho.mqtt.client as mqtt

from const import *


class SensorUpdator:

    def __init__(self):
        self.use_mqtt = bool(os.getenv("MQTT_URL"))
        self._mqtt_client = None
        self._discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant")
        self._state_prefix = os.getenv("MQTT_STATE_PREFIX", "sgcc_electricity")
        self._published_configs = set()

        if self.use_mqtt:
            self._mqtt_init()
            logging.info(
                f"MQTT enabled. discovery_prefix={self._discovery_prefix}, state_prefix={self._state_prefix}"
            )
        else:
            HASS_URL = os.getenv("HASS_URL")
            HASS_TOKEN = os.getenv("HASS_TOKEN")
            self.base_url = HASS_URL[:-1] if HASS_URL.endswith("/") else HASS_URL
            self.token = HASS_TOKEN
            logging.info("MQTT disabled. Using Homeassistant REST API.")
        self.RECHARGE_NOTIFY = os.getenv("RECHARGE_NOTIFY", "false").lower() == "true"

    def update_one_userid(self, user_id: str, balance: float, last_daily_date: str, last_daily_usage: float, yearly_charge: float, yearly_usage: float, month_charge: float, month_usage: float):
        postfix = f"_{user_id[-4:]}"
        if balance is not None:
            self.balance_notify(user_id, balance)
            self.update_balance(postfix, balance)
        if last_daily_usage is not None:
            self.update_last_daily_usage(postfix, last_daily_date, last_daily_usage)
        if yearly_usage is not None:
            self.update_yearly_data(postfix, yearly_usage, usage=True)
        if yearly_charge is not None:
            self.update_yearly_data(postfix, yearly_charge)
        if month_usage is not None:
            self.update_month_data(postfix, month_usage, usage=True)
        if month_charge is not None:
            self.update_month_data(postfix, month_charge)

        logging.info(f"User {user_id} state-refresh task run successfully!")

    def update_last_daily_usage(self, postfix: str, last_daily_date: str, sensorState: float):
        sensorName = DAILY_USAGE_SENSOR_NAME + postfix
        request_body = {
            "state": sensorState,
            "unique_id": sensorName,
            "attributes": {
                "last_reset": last_daily_date,
                "unit_of_measurement": "kWh",
                "icon": "mdi:lightning-bolt",
                "device_class": "energy",
                "state_class": "measurement",
            },
        }

        if self.use_mqtt:
            self._publish_mqtt_sensor(
                sensorName,
                sensorState,
                request_body["attributes"],
                device_class="energy",
                state_class="measurement",
                unit="kWh",
                icon="mdi:lightning-bolt",
            )
        else:
            self.send_url(sensorName, request_body)
        logging.info(f"Homeassistant sensor {sensorName} state updated: {sensorState} kWh")

    def update_balance(self, postfix: str, sensorState: float):
        sensorName = BALANCE_SENSOR_NAME + postfix
        last_reset = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")
        request_body = {
            "state": sensorState,
            "unique_id": sensorName,
            "attributes": {
                "last_reset": last_reset,
                "unit_of_measurement": "CNY",
                "icon": "mdi:cash",
                "device_class": "monetary",
                "state_class": "total",
            },
        }

        if self.use_mqtt:
            self._publish_mqtt_sensor(
                sensorName,
                sensorState,
                request_body["attributes"],
                device_class="monetary",
                state_class="total",
                unit="CNY",
                icon="mdi:cash",
            )
        else:
            self.send_url(sensorName, request_body)
        logging.info(f"Homeassistant sensor {sensorName} state updated: {sensorState} CNY")

    def update_month_data(self, postfix: str, sensorState: float, usage=False):
        sensorName = (
            MONTH_USAGE_SENSOR_NAME + postfix
            if usage
            else MONTH_CHARGE_SENSOR_NAME + postfix
        )
        current_date = datetime.now()
        first_day_of_current_month = current_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        last_reset = last_day_of_previous_month.strftime("%Y-%m")
        request_body = {
            "state": sensorState,
            "unique_id": sensorName,
            "attributes": {
                "last_reset": last_reset,
                "unit_of_measurement": "kWh" if usage else "CNY",
                "icon": "mdi:lightning-bolt" if usage else "mdi:cash",
                "device_class": "energy" if usage else "monetary",
                "state_class": "measurement",
            },
        }

        if self.use_mqtt:
            self._publish_mqtt_sensor(
                sensorName,
                sensorState,
                request_body["attributes"],
                device_class="energy" if usage else "monetary",
                state_class="measurement",
                unit="kWh" if usage else "CNY",
                icon="mdi:lightning-bolt" if usage else "mdi:cash",
            )
        else:
            self.send_url(sensorName, request_body)
        logging.info(f"Homeassistant sensor {sensorName} state updated: {sensorState} {'kWh' if usage else 'CNY'}")

    def update_yearly_data(self, postfix: str, sensorState: float, usage=False):
        sensorName = (
            YEARLY_USAGE_SENSOR_NAME + postfix
            if usage
            else YEARLY_CHARGE_SENSOR_NAME + postfix
        )
        if datetime.now().month == 1:
            last_year = datetime.now().year -1 
            last_reset = datetime.now().replace(year=last_year).strftime("%Y")
        else:
            last_reset = datetime.now().strftime("%Y")
        request_body = {
            "state": sensorState,
            "unique_id": sensorName,
            "attributes": {
                "last_reset": last_reset,
                "unit_of_measurement": "kWh" if usage else "CNY",
                "icon": "mdi:lightning-bolt" if usage else "mdi:cash",
                "device_class": "energy" if usage else "monetary",
                "state_class": "total_increasing",
            },
        }
        if self.use_mqtt:
            self._publish_mqtt_sensor(
                sensorName,
                sensorState,
                request_body["attributes"],
                device_class="energy" if usage else "monetary",
                state_class="total_increasing" if usage else "total",
                unit="kWh" if usage else "CNY",
                icon="mdi:lightning-bolt" if usage else "mdi:cash",
            )
        else:
            self.send_url(sensorName, request_body)
        logging.info(f"Homeassistant sensor {sensorName} state updated: {sensorState} {'kWh' if usage else 'CNY'}")

    def send_url(self, sensorName, request_body):
        headers = {
            "Content-Type": "application-json",
            "Authorization": "Bearer " + self.token,
        }
        url = self.base_url + API_PATH + sensorName  # /api/states/<entity_id>
        try:
            response = requests.post(url, json=request_body, headers=headers)
            logging.debug(
                f"Homeassistant REST API invoke, POST on {url}. response[{response.status_code}]: {response.content}"
            )
        except Exception as e:
            logging.error(f"Homeassistant REST API invoke failed, reason is {e}")

    def _mqtt_init(self):
        mqtt_url = os.getenv("MQTT_URL")
        parsed = urlparse(mqtt_url)
        host = parsed.hostname or mqtt_url
        port = parsed.port or 1883
        client_id = os.getenv("MQTT_CLIENT_ID", "sgcc_electricity")
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")

        client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            client.username_pw_set(username, password)
        client.connect(host, port, keepalive=60)
        self._mqtt_client = client

    def _publish_mqtt_sensor(self, sensor_name, state, attributes, device_class, state_class, unit, icon):
        if not self._mqtt_client:
            logging.error("MQTT client is not initialized.")
            return

        object_id = sensor_name.replace("sensor.", "")
        device_id = f"sgcc_electricity_{object_id[-4:]}"
        config_topic = f"{self._discovery_prefix}/sensor/{device_id}/{object_id}/config"
        state_topic = f"{self._state_prefix}/{device_id}/{object_id}/state"
        attr_topic = f"{self._state_prefix}/{device_id}/{object_id}/attributes"

        if config_topic not in self._published_configs:
            config_payload = {
                "name": object_id,
                "unique_id": object_id,
                "state_topic": state_topic,
                "json_attributes_topic": attr_topic,
                "device_class": device_class,
                "state_class": state_class,
                "unit_of_measurement": unit,
                "icon": icon,
                "device": {
                    "identifiers": [device_id],
                    "name": f"SGCC Electricity {object_id[-4:]}",
                    "model": "sgcc_electricity",
                    "manufacturer": "ARC-MX",
                },
            }
            self._mqtt_client.publish(config_topic, json.dumps(config_payload), retain=True)
            self._published_configs.add(config_topic)
            logging.info(f"MQTT discovery published: {config_topic}")

        self._mqtt_client.publish(state_topic, str(state), retain=True)
        self._mqtt_client.publish(attr_topic, json.dumps(attributes), retain=True)
        logging.info(f"MQTT state published: {state_topic}")
        logging.info(f"MQTT attributes published: {attr_topic}")

    def balance_notify(self, user_id, balance):

        if self.RECHARGE_NOTIFY :
            BALANCE = float(os.getenv("BALANCE", 10.0))
            PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN").split(",")        
            logging.info(f"Check the electricity bill balance. When the balance is less than {BALANCE} CNY, the notification will be sent = {self.RECHARGE_NOTIFY}")
            if balance < BALANCE :
                for token in PUSHPLUS_TOKEN:
                    title = "电费余额不足提醒"
                    content = (f"您用户号{user_id}的当前电费余额为：{balance}元，请及时充值。" )
                    url = ("http://www.pushplus.plus/send?token="+ token+ "&title="+ title+ "&content="+ content)
                    requests.get(url)
                    logging.info(
                        f"The current balance of user id {user_id} is {balance} CNY less than {BALANCE} CNY, notice has been sent, please pay attention to check and recharge."
                    )
        else :
            logging.info(
            f"Check the electricity bill balance, the notification will be sent = {self.RECHARGE_NOTIFY}")
            return
