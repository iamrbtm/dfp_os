# AI Agent Guide: How Dudefish Printing Parses G-Code and Calculates Print Cost

This guide explains the actual code path used by the app to:

1. accept a 3D printing file upload,
2. parse print time and filament usage,
3. convert filament length into weight,
4. calculate printing cost for that uploaded file.

It is written from the current codebase, not from intended behavior.

## Important Scope Note

The UI and business language suggest the app works with "3D printing files" in general, but the implementation only processes `.gcode` files.

- The upload form accepts `.gcode` only in [modules/products/template/product_details.html](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/template/product_details.html:604).
- The server-side processing route saves the uploaded file and parses it as G-code in [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:285).
- There is no STL or 3MF parser in the current flow.

If an AI agent is asked how the system handles STL or 3MF directly, the correct answer is: it does not. Those files would need to be sliced into G-code first.

## Data Model Used

The main tables/models involved are:

- `Product` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:218)
  - Stores per-item summary values such as `final_weight`, `final_print_time`, `items_per_plate`, and `cost`.
- `ProductGcode` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:262)
  - Stores one uploaded G-code entry with:
  - `gcode`
  - `qtyInFile`
  - `time_in_h`
  - `weight_in_kg`
  - `cost`
- `Filament` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:83)
  - Supplies `priceperroll`, `length_spool`, `diameter`, and a relation to filament `Type`.
- `Type` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:68)
  - Supplies `densitygcm3` and `kW_hr`.
- `ProductMisc` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:312)
  - Supplies extra non-material fees such as `packaging`, `advertising`, `rent`, `extrafees`, `magnet`, and `designhours`.
- `Settings` in [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:337)
  - Supplies `cost_kW` and `padding_time`.

## Upload and Parse Flow

### 1. User uploads a G-code file

The upload happens from the product details page:

- Add modal: [modules/products/template/product_details.html](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/template/product_details.html:584)
- Update modal: [modules/products/template/product_details.html](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/template/product_details.html:679)

Fields posted with the file include:

- `gcode`
- `qtyinFile`
- `printerfk`
- `filamentfk`

### 2. Server saves the file and starts processing

The POST route is `product.process(id)` in [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:285).

For `"addnew"` or `"process"` submits, it:

1. saves the uploaded file under `modules/products/static/gcode_files/`,
2. calls `calc_time_length(filepath, filamentfk)`,
3. creates a `ProductGcode` row with:
   - `qtyInFile`
   - `time_in_h`
   - `weight_in_kg`
   - file name
   - printer
   - filament

Relevant code:

- file save: [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:297)
- parse call: [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:302)
- row creation: [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:307)

### 3. G-code parser extracts duration and filament length

`calc_time_length()` in [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:10) calls `parse_gcode(filename)`.

`parse_gcode()` is in [modules/products/gcoder.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/gcoder.py:823).

It builds a `GCode` object from the file and returns:

- padded print time in hours
- filament used in millimeters

Exact return:

```python
return [(padded_seconds / 60) / 60, gcode.filament_length]
```

Source: [modules/products/gcoder.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/gcoder.py:851)

### 4. Print time padding formula

The parser applies a configurable time padding from `Settings.padding_time`:

```text
padded_seconds = gcode.duration.seconds + (gcode.duration.seconds * settings.padding_time)
```

Equivalent formula:

```text
padded_seconds = raw_duration_seconds * (1 + padding_time)
time_in_h = padded_seconds / 3600
```

Source: [modules/products/gcoder.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/gcoder.py:845)

## Filament Weight Calculation

The G-code parser returns filament length, not weight. Weight is computed in `calc_time_length()` in [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:10).

### Inputs used

From `Filament`:

- `diameter`
- related `type.densitygcm3`

Source:

- [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:83)
- [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:68)

### Conversion formula

The code converts filament length into volume, then volume into grams:

```text
filcm = length_in_m * 100
radius_cm = (diameter_mm / 2) / 10
cross_section_area_cm2 = pi * radius_cm^2
volume_cm3 = filcm * cross_section_area_cm2
weight_g = volume_cm3 * density_g_per_cm3
weight_kg = weight_g / 1000
```

This is implemented here:

- [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:11)

### End result from `calc_time_length()`

`calc_time_length()` returns:

- `time_in_h`
- `weight_in_kg`

from:

```text
parse_gcode() -> (time_in_h, length_in_mm)
length_in_mm / 1000 -> length_in_m
length_in_m -> weight_in_g
weight_in_g / 1000 -> weight_in_kg
```

## Cost Calculation for an Uploaded G-code File

The cost object is `CalcCost(gcodeID)` in [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:29).

Its purpose is to calculate the cost of one `ProductGcode` record.

## Cost Components

### 1. Filament material cost

The code computes:

```text
cost_fil_per_g = filament.priceperroll / filament.length_spool
filament_cost_plate = weight_kg * 1000 * cost_fil_per_g
filament_cost_per_item = filament_cost_plate / qtyInFile
```

Source:

- `cost_fil_per_g`: [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:47)
- `filcost()`: [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:76)

### Important unit caveat

The variable name `cost_fil_per_g` implies "cost per gram", but the formula uses:

```text
priceperroll / length_spool
```

That is only truly "cost per gram" if `length_spool` is stored in grams. If `length_spool` is actually meters or millimeters, then the formula is mislabeled and the resulting cost is wrong.

An AI agent should describe the formula exactly as coded and avoid assuming the underlying data is normalized correctly.

### 2. Electricity / machine-time cost

The time cost formula is:

```text
time_cost_plate = time_in_h * settings.cost_kW * filament.type.kW_hr
time_cost_per_item = time_cost_plate / qtyInFile
```

Source:

- [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:82)

Interpretation:

- `time_in_h` is the padded print time for the whole plate.
- `settings.cost_kW` is the electricity rate.
- `filament.type.kW_hr` is used as a power-use multiplier.

Despite the name, this is really a printer-energy cost driven by filament type metadata.

### 3. Miscellaneous fees

`CalcCost.misfees()` adds:

```text
misc_fees = packaging + advertising + rent + extrafees + (designhours * 50)
```

Source:

- [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:90)

### Important misc-fee caveats

`ProductMisc` has more fields than `CalcCost.misfees()` uses.

- `overhead` exists but is not included in `CalcCost.misfees()`.
- `magnet` exists but is not included in `CalcCost.misfees()`.

Source:

- model fields: [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:312)
- cost logic: [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:90)

### 4. Per-item subtotal for the uploaded G-code

The G-code cost calculation is:

```text
subtotal = time_cost_per_item + filament_cost_per_item + misc_fees
total = round(subtotal, 2)
```

Source:

- [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:100)

This result is then written into `new_gcode.cost`:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:335)

## What Gets Stored After Parsing

After a new G-code file is processed, the route updates:

### `ProductGcode`

- `time_in_h` = total padded plate time
- `weight_in_kg` = total plate filament weight
- `cost` = `CalcCost(new_gcode.id).total()`

Source:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:307)
- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:335)

### `Product`

The route also sets:

```text
product.final_weight = sum(ProductGcode.weight_in_kg for this product)
product.final_print_time = sum(ProductGcode.time_in_h for this product)
```

Source:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:321)

These values are plate-level totals, not per-item values, at this point.

## Final Product Cost Rollup

After processing, the route calls `update_product_cost(product.id)`:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:375)

That function computes:

```text
total_misc = packaging + advertising + rent + extrafees + (designhours * 50) + magnet
product.cost = sum(ProductGcode.cost for the product) + total_misc
```

Source:

- [modules/products/utilities.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/utilities.py:152)

## Important Pricing Behavior to Preserve in Any Explanation

An AI agent should explicitly call out these behaviors:

### 1. Misc fees are effectively counted twice in the normal parse flow

Why:

- `CalcCost.total()` already includes misc fees and gets written to `ProductGcode.cost`.
- `update_product_cost()` then sums `ProductGcode.cost` and adds misc again.

So the effective stored `product.cost` after a normal upload is:

```text
product.cost =
    (
        time_cost_per_item
        + filament_cost_per_item
        + misc_fees
    )
    + total_misc_again
```

For a single G-code row, that means misc is added twice.

### 2. `overhead` is never used in cost math

It exists on `ProductMisc`, but neither `CalcCost.misfees()` nor `update_product_cost()` adds it.

### 3. `magnet` is only added in the product rollup, not in the initial G-code cost

So:

- `ProductGcode.cost` excludes `magnet`
- `Product.cost` includes `magnet`

### 4. `padding_filament` exists in `Settings` but is not used

`Settings.padding_filament` is defined, but current parsing/cost code never applies a filament padding multiplier.

Source:

- [models.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/models.py:337)

### 5. Product details page shows per-item values by dividing the rolled-up product cost

The UI displays:

```text
Item Cost = product.cost / product.items_per_plate
Plate Cost = product.cost
```

Source:

- [modules/products/template/product_details.html](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/template/product_details.html:439)
- [modules/products/template/product_details.html](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/template/product_details.html:466)

This means what the UI calls "item cost" is derived from the rolled-up `Product.cost`, not directly from `ProductGcode.cost`.

## Manual Update Flow

There is also a manual `"update"` path in `product.process()`:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:341)

That path does not parse the file. Instead it accepts manual inputs for:

- weight
- hours
- minutes
- cost
- qty in file

Then it stores:

```text
product.final_print_time = print_time / qtyInFile
product.final_weight = (weight / qtyInFile) / 1000
```

and plate-level G-code values:

```text
ProductGcode.time_in_h = print_time
ProductGcode.weight_in_kg = weight / 1000
ProductGcode.cost = cost
```

Source:

- [modules/products/products.py](/Users/rbtm2006/Documents/Projects/WIP/dudefishprinting/modules/products/products.py:341)

This path is an override workflow, not an automatic parse workflow.

## Short Operational Summary

If an AI agent needs to summarize the current behavior in one paragraph:

The app accepts a `.gcode` upload for a product, parses the G-code to estimate total plate print duration and total filament length, applies a time-padding multiplier from settings, converts filament length to weight using filament diameter and material density, stores those plate-level values in `ProductGcode`, then calculates cost from filament usage, energy usage, and misc product fees. After that it rolls the G-code cost back into `Product.cost`, where misc fees are added again, so the final product-level cost shown in the UI is not a clean single-pass cost formula.

## Formula Summary

### Time

```text
raw_duration_seconds = parsed from G-code motion timing
padded_seconds = raw_duration_seconds * (1 + settings.padding_time)
time_in_h = padded_seconds / 3600
```

### Weight

```text
length_in_m = parsed_length_mm / 1000
radius_cm = (diameter_mm / 2) / 10
cross_section_area_cm2 = pi * radius_cm^2
volume_cm3 = (length_in_m * 100) * cross_section_area_cm2
weight_g = volume_cm3 * density_g_per_cm3
weight_kg = weight_g / 1000
```

### G-code cost as stored in `ProductGcode.cost`

```text
filament_cost_per_item = ((weight_kg * 1000) * (priceperroll / length_spool)) / qtyInFile
time_cost_per_item = (time_in_h * settings.cost_kW * filament_type.kW_hr) / qtyInFile
misc_fees = packaging + advertising + rent + extrafees + (designhours * 50)
gcode_cost = round(filament_cost_per_item + time_cost_per_item + misc_fees, 2)
```

### Final product cost as stored in `Product.cost`

```text
total_misc = packaging + advertising + rent + extrafees + (designhours * 50) + magnet
product.cost = sum(all ProductGcode.cost for the product) + total_misc
```

For a product with one G-code row, that usually means:

```text
product.cost = gcode_cost + total_misc
```

where `gcode_cost` already included most misc fees once.

