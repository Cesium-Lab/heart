
import synnax as sy
import numpy as np
from time import sleep
client = sy.Synnax(
    host="localhost",
    port=9090,
    username="synnax",
    password="seldon",
)

index_channel = client.channels.create(
    name="time_value",
    # Set is_index to True to create an index channel
    is_index=True,
    # Tell Synnax that we'll be storing timestamps in this channel
    data_type="timestamp",
    # If a channel with this name already exists, Synnax will return it instead of
    # creating a new one. This is useful if we restart the driver and want to keep the
    # existing channels.
    retrieve_if_name_exists=True,
)

data_channel = client.channels.create(
    name="sine_value",
    # Set the index to the key of the index channel, so that "sine_value" is indexed
    # by "time_value"
    index=index_channel.key,
    # Tell Synnax that we'll be storing float32s in this channel
    data_type="float32",
    # If a channel with this name already exists, Synnax will return it instead of
    # creating a new one. This is useful if we restart the driver and want to keep the
    # existing channels.
    retrieve_if_name_exists=True,
)

time = 0.0

with client.open_writer(
    # We need to provide a start time for the writer, which tells
    # Synnax where to begin writing data. We'll use the current time.
    start=sy.TimeStamp.now(),
    # The list of channels we'll be writing to.
    channels=["time_value", "sine_value"],
    # Tell Synnax to immediately persist all recorded data for
    # historical access.
    enable_auto_commit=True
) as writer:
    while True:
        # Make value
        value = np.sin(time)
        time += 0.0001
        print(f"Time: {time:.5f}, Value: {value:.5f}")
        sleep(0.001)
        writer.write({
            # The timestamp of when the data was read
            "time_value": sy.TimeStamp.now(),
            # The value from the sine function
            "sine_value": value,
       })
        