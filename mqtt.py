import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


def send_message(channel_id, message):
    mqttc = mqtt.Client(CallbackAPIVersion.VERSION2)
    mqttc.connect("localhost", 1883, 60)
    mqttc.publish(f"ledshelf/{channel_id}", message)