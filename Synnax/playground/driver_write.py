import synnax as sy
from time import time
client = sy.Synnax(
    host="localhost",
    port=9090,
    username="synnax",
    password="seldon",
)

# Create the command channel
command_channel = client.channels.create(
    name="command",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

start_time = time()

with client.open_streamer(["command"]) as streamer:
    for frame in streamer:
        # Read from the command channel
        command = str(frame["command"][0])
        # Write to the serial connection
        print(f"BUTTON WAS PRESSED at {(time() - start_time):.4f}s")