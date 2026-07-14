PMP → DFPos Integration Plan (with STL Support)
Overview
Integrate the Pack My Plate (PMP) 3D print-bed nesting engine into DFPos so users can:
- 
Select a product with a 3D model file (.3mf or .stl — binary or ASCII)
- 
Configure packing (printer/bed, count, spacing, margin, rotation step)
- 
Preview the packed layout as an SVG
- 
Save a packed 3MF file ready for the slicer (STL input gets converted to 3MF)
- 
Create PrintJobs from the pack results
Phase 1 — STL & 3MF Foundation
1.1 STL Parser (pure stdlib, zero deps)
New file: app/services/stl_parser.py
def parse_stl_vertices(path: str) -> list[tuple[float, float, float]]:
    """Return all unique vertices from a binary or ASCII STL file.
    Reads first 80 bytes; if the word 'solid' appears early it's
    ASCII, otherwise binary. Returns XY(Z) vertex list suitable
    for PMP's packing.pack() footprint extraction.
    """
- 
Binary STL: struct.unpack("<I", header[80:84]) → triangle count, then read 50-byte triangles, extract 3 vertices each (12 floats from 3f/3f/3f pattern). ~15 lines.
- 
ASCII STL: regex vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+) line by line. ~10 lines.
- 
Returns deduplicated vertex list.
Why not numpy-stl or trimesh? They add C-compiled deps. A pure-Python parser for the vertex-extraction use case is ~40 lines and avoids build/compat issues with Python 3.14.
1.2 3MF Builder (from scratch)
New file: app/services/threemf_builder.py
def build_3mf(
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    items: list[BuildItem],
    bed_w: float,
    bed_d: float,
    printer: str = "u1",
) -> bytes:
    """Build a complete 3MF zip from raw mesh data + packed transforms.
    Creates the minimal 3MF container:
    - [Content_Types].xml
    - _rels/.rels
    - 3D/3dmodel.model  (resources with mesh + build with transforms)
    - Metadata/project_settings.config  (bed dimensions, printer profile)
    """
What it constructs:
[Content_Types].xml:
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
_rels/.rels:
<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
3D/3dmodel.model: Generate <object> with the mesh vertices + triangles, then <build> with one <item> per placement carrying the transform from PMP's packing result. Reuse PMP's compose_transform() and compose_affine() for the transform math.
Metadata/project_settings.config: Reuse PMP's u1_project_settings() — it just needs bed_w, bed_d, and filament colors. For STL inputs with no color data, emit with default colors.
Key reuse from PMP:
- 
threemf.compose_transform() and threemf.compose_affine() for transform math
- 
threemf.u1_project_settings() for the project settings config
- 
threemf._fmt_bed(), threemf._fmt_float() for XML output formatting
- 
threemf.IDENTITY constant
1.3 Unify the pack pipeline in the service layer
New file: app/services/packing.py
def pack_product(
    product: Product,
    printer: Printer | None = None,
    *,
    bed_w: float | None = None,
    bed_d: float | None = None,
    count: int | None = None,
    spacing: float = 2.0,
    margin: float = 3.5,
    angle_step_deg: float = 15.0,
    pack_mode: str = "auto",
    tower: str = "auto",
) -> dict:
Pipeline:
model_path (3MF or STL)
  │
  ├── .3mf → threemf.ThreeMF.load()
  │           → extract oriented vertices + build items from source
  │
  ├── .stl → stl_parser.parse_stl_vertices()
  │           → vertices only, no build items
  │
  └── ↓
      footprint = [(x, y) for x, y, _z in vertices]
      part_height = max_z - min_z
      │
      ▼
      packing.pack(footprint, part_height, bed_w, bed_d, count, spacing, ...)
      → PackResult (placements, scale, utilization, method, warnings)
      │
      ▼
      Build items = [compose_transform(scale, rot, x, y, tz) for each placement]
      │
      ├── Source was .3mf →
      │     model.surgical_save_kwargs(bed_w, bed_d, items)
      │     → save packed 3MF via existing PMP surgery (paint-preserving)
      │
      └── Source was .stl →
            threemf_builder.build_3mf(vertices, triangles, items, bed_w, bed_d)
            → build complete 3MF zip from scratch
      │
      ▼
      SVG = packing.preview_svg(result, footprint, bed_w, bed_d, ...)
      Return {svg, stats, packed_3mf_path}
Phase 2 — Wire PMP as a Project Dependency
2.1 Add PMP to pyproject.toml
[project]
dependencies = [
    ...
    "pmp @ file://{root}/pmp",
]
Fix PMP's internal imports (multipack → local references) so it imports cleanly when installed as a path dep. Then uv lock.
Phase 3 — Packing Blueprint & UI
3.1 Blueprint boilerplate
New files:
- 
app/blueprints/packing/__init__.py
- 
app/blueprints/packing/routes.py
URL prefix: /admin/packing
3.2 Views
Route   Purpose
GET /   Product selection table (filters to products with model_file_path or converted_model_path)
GET /<product_id>/new   Pack config form: printer dropdown, count, spacing, margin, angle, mode, tower
POST /<product_id>/pack Run pack, return JSON with SVG + stats (HTMX-friendly)
GET /<product_id>/preview   Page showing the SVG preview with action buttons
POST /<product_id>/save Save packed 3MF to storage, set product.converted_model_path
POST /<product_id>/print-job    Create PrintJob linked to this product
3.3 Config form fields
- 
Printer: dropdown from Printer table (auto-fills bed_w, bed_d, has_ams)
- 
Bed width / depth: overridable, pre-filled from printer
- 
Count: "Fill bed" or specific number
- 
Spacing (mm): default 2.0
- 
Margin (mm): default 3.5 (Snapmaker U1 lift clearance)
- 
Rotation step (°): default 15.0
- 
Pack mode: auto (default), hull, bitmap, lattice
- 
Prime tower: auto (on for painted/multi-color models), off
3.4 Templates
- 
packing/select.html — Product list with model type badge (3MF/STL)
- 
packing/configure.html — Config form with printer bed visualization
- 
packing/preview.html — SVG preview inline + stats panel + action buttons
Phase 4 — API Endpoints
New file: app/blueprints/api/v1/packing.py
Method  Route   Purpose
POST    /api/v1/packing/pack    Pack a product, return SVG + stats + download URL
POST    /api/v1/packing/pack-and-create-job Pack + save 3MF + create PrintJob, return job ID
Both accept: product_id, optional printer_id, bed_w, bed_d, count, spacing, margin, angle_step, pack_mode, tower.
Phase 5 — Printer Model Enhancements
5.1 Add bed dimensions to Printer
File: app/models/fleet.py
Add fields:
bed_width_mm: Mapped[float | None] = mapped_column(nullable=True)
bed_depth_mm: Mapped[float | None] = mapped_column(nullable=True)
Seed data with fleet defaults:
Printer Bed (mm)
Bambu A1    256×256
Bambu X1 Carbon 256×256
Bambu P1P   256×256
Snapmaker U1    270×270
Migrations via flask db migrate.
Phase 6 — G-Code Pipeline (Post-Pack)
6.1 Add gcode_path to PrintJob
File: app/models/print_job.py
Add gcode_path: Mapped[str | None] mapped column.
6.2 Upload + analyze G-code
POST /admin/packing/<product_id>/upload-gcode
- 
Upload the sliced G-code (from Orca/Bambu Studio slicing the packed 3MF)
- 
Store at PrintJob.gcode_path
POST /admin/packing/<product_id>/analyze-gcode
- 
Run gcode.analyze() against the uploaded G-code
- 
Return layer stats, conflicts, pause suggestions, merge options
6.3 Post-process G-code
POST /admin/packing/<product_id>/process-gcode
- 
Accept merge choices (which filament colors to merge)
- 
Run gcode.apply_merges() → gcode.plan_swaps() → gcode.inject_pauses() → gcode.remap_tools()
- 
Save processed G-code, link to PrintJob.gcode_path
Phase 7 — Model File Upload on Product
7.1 Accept 3MF and STL uploads
Update the product form to accept both .3mf and .stl extensions on the model_file_path field.
Add a detect_model_type helper that peeks at the file extension and first bytes to classify: 3MF zip / binary STL / ASCII STL.
7.2 Show model metadata on product detail
After upload, parse and display:
- 
File type (3MF / Binary STL / ASCII STL)
- 
Vertex count
- 
3MF: paint count, object count
- 
STL: triangle count
Use the existing parsed_triangle_count and parsed_volume_mm3 fields on Product.
File Change Summary
Action  Path    Purpose
New app/services/stl_parser.py  Parse binary + ASCII STL → vertex list
New app/services/threemf_builder.py Build complete 3MF zip from raw mesh + transforms
New app/services/packing.py Orchestration: detect input type, pack, build output
New app/schemas/packing.py  Pack request/response schemas
New app/blueprints/packing/__init__.py  Blueprint definition
New app/blueprints/packing/routes.py    All packing views
New app/blueprints/api/v1/packing.py    API endpoints
New app/templates/packing/select.html   Product selection
New app/templates/packing/configure.html    Pack config form
New app/templates/packing/preview.html  SVG + stats
Edit    pyproject.toml  Add pmp path dependency
Edit    app/models/fleet.py Add bed dimensions to Printer
Edit    app/models/print_job.py Add gcode_path field
Edit    app/models/catalog.py   Accept STL extension validation
Edit    module registry Register packing module
Run uv lock Lock new deps
Run flask db migrate    Schema migrations
Supporting STL: What Changes vs. Original Plan
Original (3MF-only) With STL
threemf.ThreeMF.load() for input    stl_parser.parse_stl_vertices() + threemf_builder.build_3mf()
model.surgical_save() reuses source build items STL has no source build items → build from scratch
Only .3mf files accepted    Both .3mf and .stl accepted
Paint data preserved from source    STL has no paint → default colors in profile
No STL parsing dependency   Pure Python, no deps
Why Pure Python STL Parsing Wins Here
Approach    Pros
numpy-stl   Battle-tested, fast
trimesh Rich feature set
Custom parser (~40 lines)   Zero deps, Python 3.14 safe, trivially auditable
Custom parser is the right call. The STL spec is ~1 page, binary format hasn't changed in 30 years, and we only need vertex coordinates — not normals, not attributes, not mesh repair.
Estimated total effort: 18–24 hours (was 14–20 without STL, the STL path adds ~4 hours for the parser + 3MF builder).