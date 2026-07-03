import paho.mqtt.client as mqtt

MQTT_HOST = "localhost"
MQTT_PORT = 1883

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

def send_message(channel_id, message):
    topic = f"ledshelf/{channel_id}"
    client.publish(topic, message, retain=True)
