from typing import Final

import zigpy.types as t
from zigpy.zcl.clusters.closures import DoorLock
from zigpy.zcl.foundation import ZCLAttributeDef

from zhaquirks import DoublingPowerConfigurationCluster
from zhaquirks.builder import QuirkBuilder, SensorDeviceClass
from zhaquirks.clusters import CustomCluster
from zhaquirks.nimly import NIMLY
from zhaquirks.nimly.lock import (
    NIMLY_LOCK_NODE_DESCRIPTOR,
    last_action_source_converter,
    last_action_converter,
    last_action_user_converter,
)


class NimlyDoorLock(CustomCluster, DoorLock):
    """Nimly Door Lock cluster.

    Local copy of the upstream cluster - identical except the two custom
    attributes are no longer flagged is_manufacturer_specific, so zigpy
    can resolve their names on incoming unsolicited reports.
    """

    class AttributeDefs(DoorLock.AttributeDefs):
        """Nimly Door Lock attribute definitions."""

        nimly_last_lock_unlock_source: Final = ZCLAttributeDef(
            id=0x100,
            type=t.bitmap32,
            access="r",
        )
        nimly_last_pin_code: Final = ZCLAttributeDef(
            id=0x101,
            type=t.LVBytes,
            access="r",
        )


(
    QuirkBuilder(NIMLY, "NimlyCodePRO")
    .node_descriptor(NIMLY_LOCK_NODE_DESCRIPTOR)
    .replaces(DoublingPowerConfigurationCluster, endpoint_id=11)
    .replaces(NimlyDoorLock, endpoint_id=11)
    .sensor(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.nimly_last_lock_unlock_source.name,
        unique_id_suffix="last_action_source",
        attribute_converter=last_action_source_converter,
        device_class=SensorDeviceClass.ENUM,
        translation_key="last_action_source",
        fallback_name="Last action source",
    )
    .sensor(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.nimly_last_lock_unlock_source.name,
        unique_id_suffix="last_action",
        attribute_converter=last_action_converter,
        device_class=SensorDeviceClass.ENUM,
        translation_key="last_action",
        fallback_name="Last action",
    )
    .sensor(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.nimly_last_lock_unlock_source.name,
        unique_id_suffix="last_action_user",
        attribute_converter=last_action_user_converter,
        translation_key="last_action_user",
        fallback_name="Last action user",
    )
    .sensor(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.nimly_last_pin_code.name,
        unique_id_suffix="last_pin_code",
        attribute_converter=lambda value: value.hex(),
        initially_disabled=True,
        translation_key="last_pin_code",
        fallback_name="Last PIN code",
    )
    .switch(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.auto_relock_time.name,
        translation_key="auto_relock",
        fallback_name="Autorelock",
    )
    .number(
        endpoint_id=11,
        cluster_id=NimlyDoorLock.cluster_id,
        attribute_name=NimlyDoorLock.AttributeDefs.sound_volume.name,
        min_value=0,
        max_value=2,
        step=1,
        translation_key="sound_volume",
        fallback_name="Sound volume",
    )
    .add_to_registry()
)
