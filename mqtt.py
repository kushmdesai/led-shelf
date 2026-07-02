import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

mqttc = mqtt.Client(CallbackAPIVersion.VERSION2)
mqttc.connect("localhost", 1883, 60)
mqttc.publish("ledshelf/power", "ON")