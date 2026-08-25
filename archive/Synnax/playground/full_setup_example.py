
import synnax as sy
import numpy as np
from time import time, sleep

client = sy.Synnax(
    host="localhost",
    port=9090,
    username="synnax",
    password="seldon",
)

index_channel = client.channels.create(
    name="time_value",
    is_index=True,
    data_type="timestamp",
    retrieve_if_name_exists=True,
)

# ------------------------------------------------------------------------
#                       PTs and TCs
# ------------------------------------------------------------------------

dewar_1_pt_channel = client.channels.create(
    name="dewar_1_pt_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

dewar_2_pt_channel = client.channels.create(
    name="dewar_2_pt_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

dewar_1_tc_channel = client.channels.create(
    name="dewar_1_tc_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

dewar_2_tc_channel = client.channels.create(
    name="dewar_2_tc_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

ox_tank_pt_channel = client.channels.create(
    name="ox_tank_pt_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

ox_tank_tc_channel = client.channels.create(
    name="ox_tank_tc_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

fuel_tank_pt_channel = client.channels.create(
    name="fuel_tank_pt_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

fuel_tank_tc_channel = client.channels.create(
    name="fuel_tank_tc_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

chamber_pt_channel = client.channels.create(
    name="chamber_pt_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

chamber_tc_channel = client.channels.create(
    name="chamber_tc_channel",
    index=index_channel.key,
    data_type="float32",
    retrieve_if_name_exists=True,
)

# ------------------------------------------------------------------------
#                       Commands
# ------------------------------------------------------------------------


fill_1_command = client.channels.create(
    name="fill_1",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

fill_2_command = client.channels.create(
    name="fill_2",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

ox_mpv_command = client.channels.create(
    name="ox_mpv",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

fuel_mpv_command = client.channels.create(
    name="fuel_mpv",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

qd_command = client.channels.create(
    name="qd",
    data_type="uint8",
    virtual=True,
    retrieve_if_name_exists=True,
)

# ------------------------------------------------------------------------
#                       Commands
# ------------------------------------------------------------------------

# with client.open_streamer(["fill_1","fill_2","ox_mpv","fuel_mpv","qd"]) as streamer:
with client.open_streamer(["fill_1"]) as streamer:
    with client.open_writer(
        start=sy.TimeStamp.now(),
        channels=["time_value", "dewar_1_pt_channel"],
        # channels=["dewar_1_pt_channel", "dewar_1_tc_channel", "dewar_2_pt_channel", "dewar_2_tc_channel", "ox_tank_pt_channel", "ox_tank_tc_channel", "fuel_tank_pt_channel", "fuel_tank_tc_channel", "chamber_pt_channel", "chamber_tc_channel"],
        enable_auto_commit=True
    ) as writer:
        while True:
            fr = streamer.read(timeout=1.0)
            if fr is not None:
                print(fr.channels)
                # breakpoint()
                fill_1_status = str(fr["fill_1"][0])
                print(f"Fill 1 Status: {fill_1_status}")
                # fill_2_status = str(fr["fill_2"][0])
                # print(f"Fill 2 Status: {fill_2_status}")
                # ox_mpv_status = str(fr["ox_mpv"][0])
                # print(f"Ox MPV Status: {ox_mpv_status}")
                # fuel_mpv_status = str(fr["fuel_mpv"][0])
                # print(f"Fuel MPV Status: {fuel_mpv_status}")

            writer.write({
                "time_value": sy.TimeStamp.now(),
                "dewar_1_pt_channel": 5.0
            })

            sleep(1)
            # if data:
            #     split = data.split(",")
            #     writer.write({
            #         "arduino_time": sy.TimeStamp.now(),
            #         "arduino_state": int(split[0]),
            #         "arduino_value": float(split[1]),
            #     })