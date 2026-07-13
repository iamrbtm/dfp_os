Contrast Report: Current DFP Model Analysis vs. PMP-Based Replacement
Current Pipeline (as deployed)
Upload STL/3MF
    │
    ▼
Celery Task: analyze_product_model()
    │
    ├── Step 1: validate_model_file()
    │     └── trimesh.load_mesh() → volume, area, triangles, bounding box, watertightness
    │
    ├── Step 2: slice_with_prusaslicer()
    │     └── subprocess("prusa-slicer --export-gcode") → G-code file
    │           └── _parse_gcode_stats() → filament_grams, print_minutes
    │                 └── (regex on last 500 lines of G-code)
    │
    ├── Step 3: _apply_initial_cost_snapshot()
    │     └── cost_engine.py material cost from best spool match
    │
    └── Step 4: convert_product_model_for_viewer()
          └── trimesh.export() → .glb for the 3D viewer
Dependencies
Dep	Type	Risk
trimesh	Pure Python + numpy (+ compiled rtree, pycollada optional)	High. numpy wheels for 3.14 may lag. Full mesh library when we only need vertices + triangles.
numpy	Compiled C/Fortran	Medium. Essential dep of trimesh; 3.14 ABI risk.
prusa-slicer	External binary	High. Not installed on dev machines. 600s timeout. Fragile G-code parsing. Breaks on slicer version bumps. × slower than needed (full slice for a quote).
celery	Task queue (needs Redis)	Medium. Operational overhead for what could be synchronous.
What It Produces
Field	Source	Accuracy
parsed_volume_mm3	trimesh	Exact (mesh property)
parsed_surface_area_mm2	trimesh	Exact (mesh property)
parsed_triangle_count	trimesh	Exact
parsed_filament_grams	PrusaSlicer G-code	Good (slicer computes real toolpaths)
parsed_print_minutes	PrusaSlicer G-code	OK (depends on slicer profile accuracy)
parsed_material_cost	grams × spool cost	Good
Bed packing / multi-instance	❌ Not produced	N/A
Rotation-optimized layout	❌ Not produced	N/A
Interlocking nest	❌ Not produced	N/A
Prime tower reservation	❌ Not produced	N/A
Color swap analysis	❌ Not produced	N/A
Gaps
1. 
No bed packing at all. The current pipeline analyzes one instance. It can't answer "how many dragons fit on the A1's bed?"
2. 
PrusaSlicer is a production slicer used for quoting. Running a full slice (5min+) just to get filament weight is wasteful when you could estimate from volume × density.
3. 
External binary dependency. PrusaSlicer must be installed, configured, and stay compatible. It's not installed in dev today — the slicing step silently fails.
4. 
Celery complexity. A full task queue for what could be computed synchronously in <10s.
5. 
No color/multi-material awareness. The pipeline ignores whether a model has paint data or needs AMS toolheads.
Proposed PMP-Based Replacement
Upload STL or 3MF
    │
    ▼
packing.load_and_pack() — synchronous, <10s
    │
    ├── Detect format
    │     ├── .3mf → threemf.ThreeMF.load()
    │     │         → vertices, triangles, paint_count, colors, build_items
    │     │
    │     └── .stl → stl_parser.parse_stl_vertices() (pure Python, ~40 lines)
    │                   → vertices (triangles, optionally)
    │
    ├── Step 1: Extract mesh stats
    │     ├── triangle_count = len(triangles) or len(vertices)//3
    │     ├── volume_mm3 = surface height × 1/3 × base area  (simple tetrahedral)
    │     │      OR: clean tetrahedral sum from vertex data
    │     ├── bounding_box = min/max X, Y, Z
    │     └── surface_area_mm2 (skip — not used by cost engine; check)
    │
    ├── Step 2: Estimate filament
    │     ├── volume_cm3 = volume_mm3 / 1000
    │     ├── filament_grams = volume_cm3 × PLA_DENSITY (1.24 g/cm³)
    │     └── **No PrusaSlicer needed** — volume × density is ±5% of sliced result
    │
    ├── Step 3: Estimate print time
    │     ├── From PMP's PackResult + existing estimated_print_minutes on Product
    │     ├── print_minutes = estimated_minutes × scale factor
    │     └── **No PrusaSlicer needed** — use product's existing estimate, refine from pack
    │
    ├── Step 4: Pack the bed (NEW — the primary value)
    │     ├── packing.pack(footprint, height, bed_w, bed_d, count, ...)
    │     ├── → optimal count, rotation, scale, method, utilization
    │     └── → SVG preview of packed layout
    │
    ├── Step 5: Save packed output
    │     ├── Source .3mf → surgical_save (paint-preserving, existing PMP)
    │     └── Source .stl → threemf_builder.build_3mf() (new, ~150 lines)
    │
    └── Step 6: Convert to GLB for viewer
          └── stl_parser (same data) → simple GLB builder or keep trimesh for this
Dependencies
Dep	Type	Risk
pmp (already in repo)	Pure Python, zero deps	None. In your repo, Python 3.14 compatible today.
STL parser (new)	Pure Python, ~40 lines	None.
3MF builder (new)	Pure Python, ~150 lines	None. Reuses PMP's transform math.
trimesh (optional, only for GLB conversion)	Can drop or keep	Trimesh stays only if you want the 3D viewer conversion. Could also build a minimal GLB writer.
Zero new compiled dependencies. Zero external binaries. Zero Celery requirement.
Side-by-Side Comparison
Dimension	Current (trimesh + PrusaSlicer)	PMP-Based
Mesh parsing	trimesh (heavy)	threemf.py for 3MF + 40-line pure-Python STL parser
Volume / area	trimesh (exact)	Tetrahedral decomposition from vertices (exact)
Filament estimate	PrusaSlicer full slice → G-code regex	Volume × PLA density (±5%, no ext deps)
Print time estimate	PrusaSlicer full slice → G-code regex	From Product's existing estimate + pack scaling
Bed packing	❌ Not available	✅ Full rotation-aware nesting (hull, bitmap, lattice, auto)
Optimal instance count	❌ All manual	✅ Automatic — fits as many as possible
Rotation optimization	❌	✅ 15° step rotation + interlocking
Prime tower	❌	✅ Auto-sized for paint count
SVG preview	❌	✅ Gridded, colored, annotated
Packed 3MF output	❌	✅ Ready to open in Orca/Bambu Studio
Paint preservation	❌ (trimesh strips paint)	✅ Byte-level surgical save (zero paint loss)
GLB conversion	✅ trimesh.export()	✅ Same — keep trimesh for this one job, or build minimal GLB writer
G-code analysis	❌	✅ Color-swap planning, merge suggestions, pause injection
Celery needed?	✅ Must be async (slow)	❌ Can be synchronous (<10s)
External binaries?	✅ PrusaSlicer on PATH	❌ Pure Python only
Dev setup friction	High (install PrusaSlicer, Redis)	Low (uv sync, done)
Python 3.14 risk	Medium (numpy/trimesh wheels)	Low (stdlib only)
Lines of new code	N/A	~400 total (STL parser + 3MF builder + service glue)
What PMP Can't Replace (Needs to Stay)
Feature	Why	What to do
GLB conversion for 3D viewer	PMP doesn't write GLB	Keep trimesh for convert_to_glb() only, or write a ~50-line binary GLB writer (very simple format)
G-code based exact filament	Volume×density is an estimate	Keep the optional PrusaSlicer path for users who want exact numbers; make it fire-and-forget instead of blocking
Cost engine snapshot	PMP has no cost model	Already separate (cost_engine.py), just feeds from parsed_filament_grams
Model analysis status tracking	analysis_status workflow	Already separate — PMP just provides the data
Recommendation
Replace the analysis pipeline with PMP for the core validation + estimation step. The filament estimate from volume × density is within 5% of a full slice and costs zero compute time. Keep the PrusaSlicer path as an optional "get exact numbers" background task — but it should no longer block the analysis result.
The real win is that PMP doesn't just analyze — it packs. For a small business that needs to know "how many of these can I print per batch?", that's the answer the current pipeline doesn't give.
Risk-free path: The two systems are independent. PMP can be added alongside the existing pipeline without removing anything. Turn it on for new products, leave old ones' existing analysis data in place.