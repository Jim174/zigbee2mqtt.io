"""Constants for the fire alarm project state machine."""

# Alarm lifecycle states
STATE_IDLE = "idle"
STATE_MONITORING = "monitoring"
STATE_PREALARM = "prealarm"
STATE_ALARM = "alarm"
STATE_CRITICAL = "critical"
STATE_SILENCED = "silenced"
STATE_ACKED = "acked"
STATE_FAULT = "fault"
STATE_MANUAL_OVERRIDE = "manual_override"

# Risk severity levels
SEVERITY_NONE = "none"
SEVERITY_INFO = "info"
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

# Event names (internal normalized input)
EVENT_SENSOR_UPDATE = "sensor_update"
EVENT_SMOKE_UPDATE = "smoke_update"
EVENT_GAS_UPDATE = "gas_update"
EVENT_TEMPERATURE_UPDATE = "temperature_update"
EVENT_HEARTBEAT = "heartbeat"
EVENT_ACK = "ack"
EVENT_SILENCE = "silence"
EVENT_RESET = "reset"
EVENT_MANUAL_OVERRIDE = "manual_override"
EVENT_FAILSAFE = "failsafe"

# Common Home Assistant unavailable-like states
UNAVAILABLE_STATE_SET = {
    "unavailable",
    "unknown",
    "none",
    "null",
    "",
}

# Escalation phases (coarse-grained now, can be refined in later patches)
PHASE_OBSERVE = "observe"
PHASE_VERIFY = "verify"
PHASE_ALERT = "alert"
PHASE_EMERGENCY = "emergency"

DEFAULT_ESCALATION_PHASE_MAP = {
    STATE_IDLE: PHASE_OBSERVE,
    STATE_MONITORING: PHASE_OBSERVE,
    STATE_PREALARM: PHASE_VERIFY,
    STATE_ALARM: PHASE_ALERT,
    STATE_CRITICAL: PHASE_EMERGENCY,
    STATE_SILENCED: PHASE_VERIFY,
    STATE_ACKED: PHASE_VERIFY,
    STATE_FAULT: PHASE_VERIFY,
    STATE_MANUAL_OVERRIDE: PHASE_VERIFY,
}

# State ordering for monotonic escalation/de-escalation checks
STATE_PRIORITY = {
    STATE_IDLE: 0,
    STATE_MONITORING: 1,
    STATE_PREALARM: 2,
    STATE_ALARM: 3,
    STATE_CRITICAL: 4,
}
