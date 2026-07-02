import paho.mqtt.client as mqtt

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.loop_start()

def send_message(channel_id, message):
    topic = f"ledshelf/{channel_id}"
    client.publish(topic, message, retain=True)