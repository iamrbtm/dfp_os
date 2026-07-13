# Bambu Lab MQTT Printer Monitoring & Control
## Architecture Overview
┌─────────────────────┐     ┌────────────────────────────────────────┐
│   Browser (UI)      │◄───►│  Flask + Flask-SocketIO                │
│   Live Dashboard    │     │  ┌────────────────────────────────┐    │
│   via WebSocket     │     │  │MQTT Manager (background thread)│    │
│                     │     │  │  ┌────────────────────────┐    │    │
│   Print Job Views   │     │  │  │  PrinterMQTTClient     │────┼────┤──► MQTT Broker
│   Printer Detail    │     │  │  │  (per printer)         │    │    │    (local:8883 or
│                     │     │  │  └────────────────────────┘    │    │     cloud:8883)
│   Camera Viewer     │     │  │  ┌────────────────────────┐    │    │
│                     │     │  │  │  Camera Reader         │────┼────┤──► Camera Stream
│                     │     │  │  │  (JPEG / RTSP)         │    │    │    (port 6000 / 322)
│                     │     │  │  └────────────────────────┘    │    │
│                     │     │  └────────────────────────────────┘    │
│                     │     │                                        │
│                     │     │  ┌────────────────────────────────┐    │
│                     │     │  │  Print Sync Service            │    │
│                     │     │  │  Notification Service          │    │
│                     │     │  │  Audit Logger                  │    │
│                     │     │  └────────────────────────────────┘    │
│                     │     │                                        │
│                     │     │  ┌────────────────────────────────┐    │
│                     │     │  │  Database (MariaDB)            │    │
│                     │     │  │  ─ printers                    │    │
│                     │     │  │  ─ print_jobs                  │    │
│                     │     │  │  ─ printer_events              │    │
│                     │     │  └────────────────────────────────┘    │
│                     │     └────────────────────────────────────────┘
└─────────────────────┘
## Background: Bambu Lab MQTT Protocol
Bambu Lab printers expose MQTT over TLS on port 8883 via two modes:
### Local Mode (LAN-Only / Developer Mode)
| Field | Value |
|---|---|
| Broker | `<printer-ip>:8883` |
| TLS | Required (self-signed cert — accepts `CERT_NONE`) |
| Username | `bblp` |
| Password | LAN access code (from printer screen: Settings → Network → LAN Only Mode) |
| Subscribe | `device/{serial}/report` |
| Publish | `device/{serial}/request` |
### Cloud Mode
| Field | Value |
|---|---|
| Broker | `us.mqtt.bambulab.com:8883` |
| TLS | Required |
| Username | Bambu user ID (`u_{user_id}` or raw numeric ID) |
| Password | Cloud MQTT access token |
| Subscribe | `device/{serial}/report` |
| Publish | `device/{serial}/request` |
### Supported Printers
| Series | MQTT | Camera | Notes |
|---|---|---|---|
| A1 / A1 Mini | Port 8883 (TLS) | JPEG on port 6000 | ESP32-based, full local support |
| P1P / P1S | Port 8883 (TLS) | JPEG on port 6000 | ESP32-based, full local support |
| X1 / X1C / X1E | Port 8883 (TLS) | RTSP on port 322 | Linux-based, requires `av` for camera |
### MQTT Topics
| Topic | Direction | Purpose |
|---|---|---|
| `device/{serial}/report` | Subscribe | Status updates and command responses |
| `device/{serial}/request` | Publish | Commands and control |
### Print Commands
```json
{"print": {"command": "pause", "sequence_id": "1"}}
{"print": {"command": "resume", "sequence_id": "2"}}
{"print": {"command": "stop", "sequence_id": "3"}}
{"print": {"command": "pushall", "sequence_id": "4"}}
Full Status (pushall) Response Structure
The report JSON contains a print object with 60+ fields. Key fields:
Temperatures:
  nozzle_temper, nozzle_target_temper
  bed_temper, bed_target_temper
  chamber_temper
Print Progress:
  gcode_state        — IDLE | RUNNING | PAUSE | FAILED | FINISH
  mc_percent         — 0-100
  mc_remaining_time  — seconds
  layer_num, total_layer_num
  subtask_name       — print file display name
  gcode_file         — internal file path
  print_type         — idle | cloud_file | local
Speed:
  spd_mag            — speed percentage
  spd_lvl            — speed level (0-4)
AMS:
  ams                — array of AMS units
  ams[].tray_info[]  — tray color, type, remaining percentage
Errors:
  hms_error          — array of error codes
  hms_warning        — array of warning codes
Data Model Changes
Printer Model — New Fields
class MQTTMode(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"
# Fields to add to Printer model:
mqtt_enabled: bool              # indexed
mqtt_mode: str | None           # "local" | "cloud"
ip_address: str | None          # local IP (for local mode)
lan_access_code_encrypted: str | None   # Fernet-encrypted
cloud_user_id: str | None               # Bambu user ID (for cloud mode)
cloud_auth_token_encrypted: str | None  # Fernet-encrypted
last_seen_at: datetime | None
last_mqtt_status: dict | None   # MySQL JSON column — latest full status blob
mqtt_connected: bool
camera_enabled: bool
camera_last_frame_at: datetime | None
PrinterEvent Model — New Table
class PrinterEvent(db.Model):
    __tablename__ = "printer_events"
    printer_id: FK → printers.id     # indexed
    event_type: str                   # indexed — see event types below
    event_data: dict | None           # MySQL JSON
    occurred_at: datetime             # indexed
    created_at: datetime
Event types: print_started, print_completed, print_failed, print_paused, print_resumed, printer_online, printer_offline, error, filament_change, ams_update
PrintJob Model — New Fields
gcode_file: str | None
subtask_name: str | None
printer_job_id: str | None           # printer's internal job ID
last_synced_at: datetime | None
current_layer: int | None
total_layers: int | None
print_percentage: Decimal(5,2) | None
estimated_remaining_seconds: int | None
nozzle_temp: Decimal(5,1) | None
bed_temp: Decimal(5,1) | None
mqtt_sync_enabled: bool              # default True
sync_conflict: bool                  # True when manual edit diverges
Dependencies
Add to pyproject.toml:
"paho-mqtt>=2.1.0"
"flask-socketio>=5.5.0"
"simple-websocket>=1.1.0"     # Flask-SocketIO transport
"av>=14.0.0"                  # RTSP for X1C camera
"cryptography>=44.0.0"        # Fernet encryption for credentials
Service Layer: app/services/printer_mqtt/
printer_mqtt/
  __init__.py
  encryption.py         # Fernet encrypt/decrypt for stored credentials
  client.py             # PrinterMQTTClient — paho-mqtt per printer
  manager.py            # PrinterMQTTManager — singleton, manages all clients
  commands.py           # Command JSON builders
  parser.py             # Status message normalization
  print_sync.py         # Auto-sync PrintJob records from MQTT events
  camera.py             # Camera frame reader (JPEG + RTSP)
encryption.py
- 
init_encryption(app) — derive Fernet key from SECRET_KEY
- 
encrypt(plaintext: str) -> str
- 
decrypt(ciphertext: str) -> str
client.py — PrinterMQTTClient
Manages a single MQTT connection per printer:
- 
__init__(printer_id, serial, mode, host, port, username, password)
- 
connect() — TLS connection, subscribe to device/{serial}/report, send pushall
- 
disconnect() — graceful cleanup
- 
send_command(command_dict) — publish to device/{serial}/request
- 
is_connected() -> bool
- 
Auto-reconnect with exponential backoff (5s → 300s)
- 
Heartbeat: pushall every 30s when connected
- 
Callbacks (to manager): on_status(status_dict), on_connected(), on_disconnected(reason_code)
- 
TLS: cert_reqs=ssl.CERT_NONE for self-signed printer certs
manager.py — PrinterMQTTManager (Singleton)
- 
start(app) — loads all mqtt_enabled=True printers from DB, starts clients
- 
stop() — gracefully disconnect all clients
- 
restart_printer(printer_id) — reconnect single printer (e.g. after config change)
- 
send_command(printer_id, command_dict) — route command to correct client
- 
get_camera_frame(printer_id) -> bytes | None — get latest cached frame
- 
active_clients() -> list[PrinterMQTTClient] — connected clients
- 
Status routing: update DB → emit SocketIO → trigger print_sync → create event → fire notification
- 
Thread-safe: each client runs loop_start() in its own thread
commands.py
Pure functions returning command JSON dicts:
def pause(seq: int) -> dict
def resume(seq: int) -> dict
def stop(seq: int) -> dict
def light_on(seq: int) -> dict
def light_off(seq: int) -> dict
def pushall(seq: int) -> dict
def set_speed(pct: int, seq: int) -> dict
parser.py
Normalizes printer JSON into a structured PrinterStatus dataclass:
@dataclass
class PrinterStatus:
    gcode_state: str                    # IDLE | RUNNING | PAUSE | FAILED | FINISH
    print_percentage: float | None
    remaining_time_seconds: int | None
    current_layer: int | None
    total_layers: int | None
    nozzle_temp: float | None
    nozzle_target: float | None
    bed_temp: float | None
    bed_target: float | None
    chamber_temp: float | None
    fan_speed: int | None
    speed_level: int | None
    speed_magnification: int | None
    subtask_name: str | None
    gcode_file: str | None
    print_type: str | None
    ams_data: list[dict] | None        # tray info per AMS
    errors: list[dict] | None
    warnings: list[dict] | None
def parse_report(payload: dict) -> PrinterStatus
def parse_ams(payload: dict) -> list[dict]
def parse_errors(payload: dict) -> list[dict]
print_sync.py — MQTT-Driven Print Job State Machine
Automatic PrintJob lifecycle from MQTT events:
MQTT State Change   PrintJob Action
IDLE → RUNNING  Find matching PrintJob by printer + queued status, or auto-create new one. Set status=PRINTING, started_at=now, store gcode_file, subtask_name
RUNNING progress    Update print_percentage, current_layer, total_layers, estimated_remaining_seconds, nozzle_temp, bed_temp, last_synced_at
RUNNING → FINISH    Set status=COMPLETED, completed_at=now, actual_minutes from remaining time
RUNNING → FAILED    Set status=FAILED, failure_reason from error codes
RUNNING → PAUSE Set status=PAUSED
PAUSE → RUNNING Set status=PRINTING
Any → IDLE  No active print. Clear sync reference.
camera.py — PrinterCameraReader
class PrinterCameraReader:
    A1_JPEG_PORT = 6000
    X1_RTSP_PORT = 322
    def __init__(self, printer)
    def get_frame() -> bytes | None
    # A1/P1/P1S: JPEG stream over TLS port 6000
    #   Send auth packet (4 bytes serial len + serial bytes + 4 zero bytes)
    #   Read raw JPEG boundary-delimited stream
    #   Return latest complete JPEG
    # X1/X1C/X1E: RTSP on port 322
    #   Use av.open(f"rtsp://{ip}:322/stream?username=&password=")
    #   Decode one frame, encode as JPEG bytes
WebSocket Layer (Flask-SocketIO)
Setup
# app/extensions.py
from flask_socketio import SocketIO
socketio = SocketIO()
Namespace: /printer
Client Event    Handler Action
connect Authenticate via Flask session or token
subscribe_printer   Join room printer:{id}
unsubscribe_printer Leave room printer:{id}
request_camera_frame    Read camera, emit camera_frame back to requester
Server Emit Condition
printer_status  Any MQTT status update — room printer:{id}
printer_event   Any PrinterEvent — room printer:{id}
camera_frame    Camera frame available — room printer:{id}:camera
printer_list_update Broadcast to all (printer online/offline changes)
App Factory Integration
def create_app():
    app = Flask(__name__)
    socketio.init_app(app, cors_allowed_origins="*", path="/ws/printer")
    from app.socketio_events import *
    return app
Configuration
app/config.py
MQTT_ENABLED = _as_bool(os.getenv("MQTT_ENABLED"), False)
MQTT_POLL_INTERVAL_SECONDS = int(os.getenv("MQTT_POLL_INTERVAL_SECONDS", "30"))
MQTT_RECONNECT_DELAY_MIN = int(os.getenv("MQTT_RECONNECT_DELAY_MIN", "5"))
MQTT_RECONNECT_DELAY_MAX = int(os.getenv("MQTT_RECONNECT_DELAY_MAX", "300"))
.env.example
MQTT_ENABLED=false
MQTT_POLL_INTERVAL_SECONDS=30
MQTT_RECONNECT_DELAY_MIN=5
MQTT_RECONNECT_DELAY_MAX=300
Route & API Endpoints
Blueprint Routes (app/blueprints/printers/routes.py)
All require STAFF+ role. Return JSON. Audit-logged.
Method  Route   Action
POST    /printers/<id>/mqtt/pause   Pause current print
POST    /printers/<id>/mqtt/resume  Resume paused print
POST    /printers/<id>/mqtt/stop    Stop/cancel print
POST    /printers/<id>/mqtt/light   Toggle light {"on": true/false}
POST    /printers/<id>/mqtt/refresh Request pushall status dump
POST    /printers/<id>/mqtt/test    Test MQTT connection
GET /printers/live  Live dashboard page
API Endpoints (/api/v1/)
Token-authenticated, gated by feature flag module.printer_mqtt.enabled.
Method  Route   Action
POST    /api/v1/printers/<id>/mqtt/pause    Pause
POST    /api/v1/printers/<id>/mqtt/resume   Resume
POST    /api/v1/printers/<id>/mqtt/stop Stop
POST    /api/v1/printers/<id>/mqtt/light    Toggle light
GET /api/v1/printers/<id>/mqtt/status   Latest cached status
UI Pages
Live Dashboard — /printers/live
WebSocket-connected real-time printer overview:
- 
Card per printer with connection status dot, progress bar, nozzle/bed temps, layer progress, ETA, active filename, AMS tray indicators, quick action buttons, camera thumbnail
Printer Detail — /printers/<id>
Enhanced with MQTT connection panel, live status section, event timeline, camera view, command buttons, MQTT config editor.
Camera Viewer
Inline expandable view with auto-refresh via WebSocket, expandable to full-size modal.
Forms
PrinterForm — New MQTT Fields
- 
MQTT enabled toggle
- 
Mode selector (local / cloud)
- 
Conditional fields: IP + LAN code (local) or user ID + token (cloud)
- 
Camera enable toggle
- 
Test Connection button (HTMX)
Module Registry
ModuleDefinition(
    key="printer_mqtt",
    display_name="Printer MQTT",
    description="Real-time MQTT monitoring and control for Bambu Lab printers.",
    feature_flag_key="module.printer_mqtt.enabled",
    default_enabled=False,
    dependencies=("printers",),
    blueprint_names=("printers",),
    api_resources=(),
    required_roles=("admin", "staff"),
    admin_nav_entries=(NavEntry("Live Printers", "printers.live_dashboard"),),
)
Celery Tasks — app/tasks/printer_mqtt.py
Task    Schedule    Purpose
printer_mqtt.poll   Every 60s   Send pushall to all connected printers
printer_mqtt.camera_snapshot    Every 10s   Capture camera frame (only if viewers active)
printer_mqtt.health Every 300s  Check connections, reconnect stale clients
Notification Triggers
Event   Notification
Print completed "Print Complete: {name} on {printer} ({duration})"
Print failed    "Print Failed: {name} on {printer} — {error}"
Printer disconnected    "Printer {name} disconnected (no response for {minutes}m)"
Printer reconnected "Printer {name} reconnected"
Audit Events
Action  Entity Type When
printer.mqtt_connected  printer Client connects
printer.mqtt_disconnected   printer Client disconnects
printer.mqtt_command_sent   printer Command published
print_job.started_mqtt  print_job   MQTT reports RUNNING
print_job.completed_mqtt    print_job   MQTT reports FINISH
print_job.failed_mqtt   print_job   MQTT reports FAILED
File Change Summary
New Files
app/services/printer_mqtt/__init__.py
app/services/printer_mqtt/encryption.py
app/services/printer_mqtt/client.py
app/services/printer_mqtt/manager.py
app/services/printer_mqtt/commands.py
app/services/printer_mqtt/parser.py
app/services/printer_mqtt/print_sync.py
app/services/printer_mqtt/camera.py
app/socketio_events.py
app/tasks/printer_mqtt.py
app/templates/printers/live.html
app/templates/printers/_mqtt_panel.html
app/templates/printers/_printer_card.html
app/templates/printers/_camera_view.html
tests/test_printer_mqtt.py
migrations/XXXX_extend_printers_for_mqtt.py
migrations/XXXX_create_printer_events.py
docs/printer_mqtt_setup.md
Modified Files
File    Change
app/models/fleet.py Add MQTT fields, PrinterEvent, MQTTMode enum
app/models/print_job.py Add MQTT sync fields
app/models/__init__.py  Export PrinterEvent
app/forms/fleet.py  Add MQTT form fields
app/blueprints/printers/routes.py   Add MQTT command routes, live dashboard
app/blueprints/printers/__init__.py Register new routes
app/module_registry.py  Register printer_mqtt module, nav entry
app/config.py   Add MQTT config vars
app/extensions.py   Add SocketIO
app/__init__.py Init MQTT manager + SocketIO
pyproject.toml  Add paho-mqtt, flask-socketio, av, cryptography
.env.example    Add MQTT env vars
app/tasks/__init__.py   Register beat schedule
Test Plan
Test    What It Covers
test_mqtt_client_connect_local  Correct local connection params
test_mqtt_client_connect_cloud  Correct cloud connection params
test_mqtt_command_pause Pause JSON structure
test_mqtt_command_stop  Stop JSON structure
test_mqtt_command_light Light on/off JSON
test_mqtt_parse_idle    Parse IDLE state
test_mqtt_parse_running Parse RUNNING with progress/temps/layers
test_mqtt_parse_failed  Parse FAILED state
test_mqtt_parse_complete    Parse FINISH state
test_mqtt_parse_ams Parse AMS tray data
test_encryption_roundtrip   Encrypt/decrypt preserves plaintext
test_print_sync_creates_job MQTT start creates PrintJob
test_print_sync_updates_progress    Progress events update print_percentage
test_print_sync_marks_complete  FINISH completes PrintJob
test_print_sync_marks_failed    FAILED marks failure
test_routes_require_auth    Command routes 401 without login
test_routes_require_staff   Customer role gets 403
test_routes_audit_logged    Commands audit-logged
test_camera_a1_jpeg Camera stream connect (mocked)
test_socketio_emit_on_status    Status change emits SocketIO event
test_form_saves_mqtt_fields Form saves MQTT fields correctly
Implementation Order
 1. 
Phase 1 — Database models, migrations, encryption utility
 2. 
Phase 2 — MQTT service layer (client, parser, commands, manager)
 3. 
Phase 3 — Print job auto-sync
 4. 
Phase 4 — WebSocket layer (SocketIO setup, event handlers)
 5. 
Phase 5 — Forms and UI (extend PrinterForm, live dashboard, detail panel)
 6. 
Phase 6 — Command routes and API endpoints
 7. 
Phase 7 — Camera integration
 8. 
Phase 8 — Celery tasks
 9. 
Phase 9 — Notifications and audit
10. 
Phase 10 — Module registry, feature flags, config
11. 
Phase 11 — Tests
12. 
Phase 12 — Documentation (docs/printer_mqtt_setup.md)
References
- 
Doridian/OpenBambuAPI (https://github.com/Doridian/OpenBambuAPI) — community MQTT protocol documentation
- 
paho-mqtt (https://pypi.org/project/paho-mqtt/) — Python MQTT client library
- 
Flask-SocketIO (https://flask-socketio.readthedocs.io/) — WebSocket integration
- 
coelacant1/Bambu-Lab-Cloud-API (https://github.com/coelacant1/Bambu-Lab-Cloud-API) — Cloud MQTT reference
- 
christianmeurer/bambu-local (https://github.com/christianmeurer/bambu-local) — Local-only MQTT control tool (MIT)
- 
ha-bambulab (https://github.com/greghesp/ha-bambulab) — Home Assistant Bambu integration (protocol reference)