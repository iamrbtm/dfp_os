// PackMyPlate Web Worker: runs the Python nesting engine under Pyodide (WASM).
// Everything here is off the main thread and entirely local â€” the only network
// traffic is fetching Pyodide from the CDN and the same-origin engine .py files.

/* global loadPyodide */

var PYODIDE_VERSION = "v0.26.4";
var PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/" + PYODIDE_VERSION + "/full/";
importScripts(PYODIDE_BASE + "pyodide.js");

// Where the engine lives inside Pyodide's in-memory FS.
var ENGINE_DIR = "/home/pyodide/engine";

// Engine files copied by build.sh (nesting + color-swap analyzer).
var ENGINE_FILES = [
  "py/web_entry.py",
  "py/multipack/__init__.py",
  "py/multipack/threemf.py",
  "py/multipack/packing.py",
  "py/multipack/bitmap.py",
  "py/multipack/gcode.py",
  // Runtime data the engine reads next to the module (native U1 project
  // template used to reprint packed plates as native Snapmaker U1 projects).
  "py/multipack/data/u1_project_settings.json",
];

var pyodideReady = null;

function post(type, extra, transfer) {
  var msg = { type: type };
  if (extra) for (var k in extra) msg[k] = extra[k];
  if (transfer) self.postMessage(msg, transfer);
  else self.postMessage(msg);
}

async function initEngine() {
  if (pyodideReady) return pyodideReady;
  pyodideReady = (async function () {
    post("progress", { stage: "engine" });
    var pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });

    pyodide.FS.mkdirTree(ENGINE_DIR + "/multipack/data");
    // Fetch each same-origin engine file and write it into the Pyodide FS.
    await Promise.all(ENGINE_FILES.map(async function (rel) {
      var resp = await fetch(rel);
      if (!resp.ok) throw new Error("failed to load " + rel + " (" + resp.status + ")");
      var text = await resp.text();
      var dest = ENGINE_DIR + "/" + rel.replace(/^py\//, "");
      pyodide.FS.writeFile(dest, text);
    }));

    // Put the engine on sys.path and define JSON-returning drivers.
    //
    // The color-swap drivers cache the decoded G-code lines between analyze and
    // process for the same file token, so a 100 MB+ file is decoded once, not
    // twice. The cache holds a single file (freed when a new token analyzes).
    await pyodide.runPythonAsync(
      "import sys, json\n" +
      "sys.path.insert(0, " + JSON.stringify(ENGINE_DIR) + ")\n" +
      "import web_entry\n" +
      "\n" +
      "def _mp_pack(data_js, opts_js):\n" +
      "    opts = opts_js.to_py()\n" +
      "    opts = {k: v for k, v in opts.items() if v is not None or k in ('target', 'count')}\n" +
      "    try:\n" +
      "        res = web_entry.nest_bytes(bytes(data_js.to_py()), **opts)\n" +
      "    except web_entry.NestError as e:\n" +
      "        return json.dumps({'error': str(e)})\n" +
      "    return json.dumps({\n" +
      "        'svg': res['svg'],\n" +
      "        'out_path': res['out_path'],\n" +
      "        'stats': {\n" +
      "            'placed': res['placed'], 'method': res['method'],\n" +
      "            'scale': res['scale'], 'utilization': res['utilization'],\n" +
      "            'warnings': res['warnings'],\n" +
      "        },\n" +
      "    })\n" +
      "\n" +
      "_mp_lines = {'token': None, 'lines': None}\n" +
      "\n" +
      "def _mp_analyze(token, data_js, max_tools):\n" +
      "    lines = web_entry._decode(bytes(data_js.to_py()))\n" +
      "    _mp_lines['token'] = token\n" +
      "    _mp_lines['lines'] = lines  # replaces any prior file, freeing it\n" +
      "    return json.dumps(web_entry.analyze_lines(lines, max_tools=int(max_tools)))\n" +
      "\n" +
      "def _mp_process(token, merges_js, pause_cmd, max_tools):\n" +
      "    if _mp_lines['token'] != token or _mp_lines['lines'] is None:\n" +
      "        return json.dumps({'error': 'stale file; please re-analyze'})\n" +
      "    merges = [tuple(m) for m in merges_js.to_py()]\n" +
      "    out, summary = web_entry.process_lines(\n" +
      "        _mp_lines['lines'], merges, pause_cmd=pause_cmd, max_tools=int(max_tools))\n" +
      "    with open('/tmp/mp_ready.gcode', 'wb') as f:\n" +
      "        f.write(out)\n" +
      "    return json.dumps({'summary': summary, 'out_path': '/tmp/mp_ready.gcode'})\n"
    );
    return pyodide;
  })();
  return pyodideReady;
}

async function pack(bytes, opts) {
  var pyodide = await initEngine();
  post("progress", { stage: "reading" });

  var data = new Uint8Array(bytes);
  post("progress", { stage: "packing" });

  var driver = pyodide.globals.get("_mp_pack");
  var jsonStr = driver(data, opts); // JsProxy args; Python calls .to_py()
  driver.destroy();

  var out = JSON.parse(jsonStr);
  if (out.error) { post("error", { message: out.error }); return; }

  var packed = pyodide.FS.readFile(out.out_path); // Uint8Array
  var buf = packed.buffer.slice(0); // own copy so it is transferable
  post("result", { svg: out.svg, stats: out.stats, packed3mfBytes: buf }, [buf]);
}

async function analyze(token, bytes, maxTools) {
  var pyodide = await initEngine();
  post("progress", { stage: "reading" });
  var data = new Uint8Array(bytes);
  post("progress", { stage: "analyzing" });

  var driver = pyodide.globals.get("_mp_analyze");
  var jsonStr = driver(token, data, maxTools);
  driver.destroy();

  var report = JSON.parse(jsonStr);
  if (report.error) { post("error", { message: report.error }); return; }
  post("analyzed", { report: report });
}

async function process(token, merges, pauseCmd, maxTools) {
  var pyodide = await initEngine();
  post("progress", { stage: "processing" });

  var driver = pyodide.globals.get("_mp_process");
  // Pass the JS array straight through; Python calls .to_py() on the JsProxy.
  var jsonStr = driver(token, merges, pauseCmd, maxTools);
  driver.destroy();

  var out = JSON.parse(jsonStr);
  if (out.error) { post("error", { message: out.error }); return; }

  var ready = pyodide.FS.readFile(out.out_path); // Uint8Array
  var buf = ready.buffer.slice(0); // own copy so it is transferable
  post("processed", { summary: out.summary, gcodeBytes: buf }, [buf]);
}

onmessage = async function (e) {
  var msg = e.data || {};
  try {
    if (msg.type === "pack") {
      await pack(msg.bytes, msg.opts);
    } else if (msg.type === "analyze") {
      await analyze(msg.token, msg.bytes, msg.maxTools);
    } else if (msg.type === "process") {
      await process(msg.token, msg.merges, msg.pauseCmd, msg.maxTools);
    }
  } catch (err) {
    post("error", { message: (err && err.message) || String(err) });
  }
};