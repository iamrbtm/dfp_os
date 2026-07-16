(function () {
  "use strict";

  var POLL_TIMEOUT_MS = 120000;

  function getCSRFToken() {
    var meta = document.querySelector("meta[name='csrf-token']");
    if (meta) return meta.getAttribute("content");
    var input = document.querySelector("[name='csrf_token']");
    if (input) return input.value;
    var cookie = document.cookie.match(/csrf_token=([^;]+)/);
    if (cookie) return cookie[1];
    return "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    initModelUpload();
    initCostCalculation();
    initReanalyze();
    initImageManagement();
    initUploadSettingsModal();
    initAssetsModal();
  });

  function initModelUpload() {
    var dropZone = document.getElementById("model-drop-zone");
    var fileInput = document.getElementById("model_file");
    var uploadForm = document.getElementById("model-upload-form");

    if (!dropZone || !fileInput || !uploadForm) return;
    var productId = uploadForm.getAttribute("data-product-id");
    if (!productId) return;

    dropZone.addEventListener("click", function (e) {
      e.preventDefault();
      fileInput.click();
    });

    ["dragenter", "dragover"].forEach(function (eventName) {
      dropZone.addEventListener(eventName, function (e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add("border-primary");
      });
    });

    dropZone.addEventListener("dragleave", function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("border-primary");
    });

    dropZone.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("border-primary");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        updateDropZoneLabel(e.dataTransfer.files[0].name);
      }
    });

    document.addEventListener("dragover", preventUnhandledFileDrop);
    document.addEventListener("drop", preventUnhandledFileDrop);

    fileInput.addEventListener("change", function () {
      if (fileInput.files.length) {
        updateDropZoneLabel(fileInput.files[0].name);
      }
    });

    uploadForm.addEventListener("submit", function (e) {
      e.preventDefault();

      var formData = new FormData(uploadForm);
      var btn = uploadForm.querySelector("[type='submit']");
      var modalError = document.getElementById("upload-settings-error");
      if (modalError) {
        modalError.classList.add("hidden");
        modalError.textContent = "";
      }
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Uploading...";
      }

      fetch("/products/studio/" + productId + "/upload-model", {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().then(function (d) {
              throw new Error(d.error || "Upload failed");
            });
          }
          return r.json();
        })
        .then(function (data) {
          setModalOpen(document.getElementById("upload-settings-modal"), false);
          showFlash("Model uploaded. Analysis started.", "success");
          updateLiveProgress({step: "queued", percent: 2, message: "Upload complete; analysis queued"});
          if (data.task_id) {
            pollTask(data.task_id, function (result) {
              updateLiveProgress({step: "complete", percent: 100, message: "Model analysis complete"});
              refreshAnalysisResult(productId);
              if (result && result.convert_task_id) {
                pollTask(result.convert_task_id, function () {
                  updateLiveProgress({step: "complete", percent: 100, message: "Analysis and GLB preview complete"});
                  refreshAnalysisResult(productId);
                }, null, function (progress) {
                  updateLiveProgress(progress, "GLB preview");
                });
              }
            }, null, updateLiveProgress);
          } else {
            updateLiveProgress({step: "uploaded", percent: 100, message: "Upload complete"});
            refreshAnalysisResult(productId);
          }
        })
        .catch(function (err) {
          showFlash(err.message || "Upload failed.", "danger");
          if (modalError) {
            modalError.textContent = err.message || "Upload failed.";
            modalError.classList.remove("hidden");
          }
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Upload & Analyze";
          }
        });
    });
  }

  function setModalOpen(modal, open) {
    if (!modal) return;
    modal.classList.toggle("hidden", !open);
    modal.classList.toggle("flex", open);
    document.body.style.overflow = open ? "hidden" : "";
  }

  function updateLiveProgress(progress, prefix) {
    progress = progress || {};
    var container = document.getElementById("analysis-live-status");
    if (!container) return;
    var percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    container.classList.remove("hidden");
    document.getElementById("analysis-live-message").textContent = (prefix ? prefix + ": " : "") + (progress.message || "Processing model");
    document.getElementById("analysis-live-percent").textContent = Math.round(percent) + "%";
    document.getElementById("analysis-live-bar").style.width = percent + "%";
    document.getElementById("analysis-live-step").textContent = String(progress.step || "working").replace(/_/g, " ");
  }

  function refreshAnalysisResult(productId) {
    fetch("/products/studio/" + productId + "/analysis-result", {headers: {"Accept": "application/json"}})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var status = document.getElementById("product-analysis-status");
        var time = document.getElementById("product-analysis-time");
        var material = document.getElementById("product-analysis-material-cost");
        if (status) status.textContent = data.status || "none";
        if (time && data.print_minutes != null) time.textContent = Math.round(data.print_minutes) + " min";
        if (material && data.material_cost != null) material.textContent = "$" + Number(data.material_cost).toFixed(2);
      });
  }

  function initUploadSettingsModal() {
    var modal = document.getElementById("upload-settings-modal");
    var openButton = document.getElementById("open-upload-settings");
    var fileInput = document.getElementById("model_file");
    if (!modal || !openButton || !fileInput) return;

    function openSettings() {
      if (!fileInput.files.length) {
        fileInput.click();
        return;
      }
      setModalOpen(modal, true);
    }
    openButton.addEventListener("click", openSettings);
    fileInput.addEventListener("change", function () {
      if (fileInput.files.length) setModalOpen(modal, true);
    });
    modal.querySelectorAll("[data-close-upload-modal]").forEach(function (button) {
      button.addEventListener("click", function () { setModalOpen(modal, false); });
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function formatBytes(value) {
    var bytes = Number(value || 0);
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function metadataSummary(metadata) {
    if (metadata.schema === "dfpos.pmp-packed-plate") {
      var pmp = metadata.pmp || {};
      var output = metadata.output || {};
      return [
        ["Generated", metadata.generated_at], ["Source", metadata.source && metadata.source.filename],
        ["Source format", metadata.source && metadata.source.format], ["Output", output.filename],
        ["Printer profile", pmp.printer_profile], ["Bed", pmp.bed_width_mm != null ? pmp.bed_width_mm + " × " + pmp.bed_depth_mm + " mm" : null],
        ["Copies placed", pmp.placed], ["Packing method", pmp.method], ["Mode", pmp.mode],
        ["Scale", pmp.scale], ["Spacing", pmp.spacing_mm != null ? pmp.spacing_mm + " mm" : null],
        ["Margin", pmp.margin_mm != null ? pmp.margin_mm + " mm" : null],
        ["Angle step", pmp.angle_step_degrees != null ? pmp.angle_step_degrees + "°" : null],
        ["Prime tower", pmp.tower], ["Bed utilization", pmp.bed_utilization != null ? (Number(pmp.bed_utilization) * 100).toFixed(1) + "%" : null],
        ["Usable utilization", pmp.usable_utilization != null ? (Number(pmp.usable_utilization) * 100).toFixed(1) + "%" : null],
        ["Output size", output.size_bytes != null ? formatBytes(output.size_bytes) : null],
        ["Warnings", (pmp.warnings || []).join("; ") || "None"]
      ].filter(function (item) { return item[1] !== undefined && item[1] !== null && item[1] !== ""; })
        .map(function (item) { return item[0] + ": " + item[1]; });
    }
    var geometry = metadata.geometry || {};
    var results = metadata.results || {};
    var slicer = metadata.slicer || {};
    var settings = [
      ["Profile", slicer.printer_profile], ["Material", slicer.material],
      ["Density", slicer.filament_density, " g/cm³"], ["Nozzle", slicer.nozzle_diameter, " mm"],
      ["Layer height", slicer.layer_height, " mm"], ["Walls", slicer.perimeters],
      ["Top layers", slicer.top_solid_layers], ["Bottom layers", slicer.bottom_solid_layers],
      ["Infill", slicer.infill_percent, "%"], ["Infill pattern", slicer.infill_pattern],
      ["Supports", slicer.supports], ["Brim", slicer.brim_width, " mm"],
      ["Copies", slicer.copies], ["Scale", slicer.scale_percent, "%"],
      ["Preserve orientation", slicer.preserve_orientation ? "Yes" : "No"],
      ["Multicolor", slicer.multicolor ? "Yes" : "No"],
      ["Use embedded 3MF", slicer.use_embedded_settings ? "Yes" : "No"],
      ["Convert to GLB", metadata.derived_assets && metadata.derived_assets.glb_requested ? "Yes" : "No"],
      ["Retain G-code", slicer.retain_gcode ? "Yes" : "No"]
    ].filter(function (item) { return item[1] !== undefined && item[1] !== null && item[1] !== ""; })
      .map(function (item) { return item[0] + ": " + item[1] + (item[2] || ""); });
    return settings.concat([
      results.filament_grams ? "Filament: " + results.filament_grams + " g" : "",
      results.print_minutes ? "Time: " + results.print_minutes + " min" : "",
      geometry.width_mm ? "Size: " + Number(geometry.width_mm).toFixed(1) + " × " + Number(geometry.depth_mm).toFixed(1) + " × " + Number(geometry.height_mm).toFixed(1) + " mm" : ""
    ].filter(Boolean));
  }

  function attachAssetMetadataPopups(grid, assets) {
    var popup = document.getElementById("asset-metadata-popup");
    if (!popup) {
      popup = document.createElement("div");
      popup.id = "asset-metadata-popup";
      popup.className = "app-card fixed hidden max-w-[calc(100vw-24px)] overflow-auto p-3 text-xs shadow-lg";
      popup.style.zIndex = "10000";
      popup.style.backgroundColor = "var(--color-surface)";
      popup.style.opacity = "1";
      popup.style.borderColor = "var(--color-border)";
      popup.style.color = "var(--color-text)";
      (grid.closest("#assets-modal") || document.body).appendChild(popup);
    }
    grid.querySelectorAll("[data-asset-index]").forEach(function (card) {
      var summary = metadataSummary((assets[Number(card.getAttribute("data-asset-index"))] || {}).metadata || {});
      if (!summary.length) return;
      card.addEventListener("mouseenter", function () {
        popup.innerHTML = '<div class="grid gap-x-5 gap-y-1 sm:grid-cols-2">' + summary.map(function (line) {
          return '<div class="whitespace-nowrap">' + escapeHtml(line) + '</div>';
        }).join("") + '</div>';
        popup.classList.remove("hidden");
        popup.style.width = Math.min(520, window.innerWidth - 24) + "px";
        popup.style.maxHeight = Math.max(180, window.innerHeight - 24) + "px";
        var rect = card.getBoundingClientRect();
        var popupRect = popup.getBoundingClientRect();
        var left = Math.min(Math.max(12, rect.left), window.innerWidth - popupRect.width - 12);
        var below = window.innerHeight - rect.bottom - 12;
        var top = below >= popupRect.height || below >= rect.top
          ? rect.bottom + 8
          : Math.max(12, rect.top - popupRect.height - 8);
        popup.style.left = left + "px";
        popup.style.top = Math.min(top, window.innerHeight - popupRect.height - 12) + "px";
      });
      card.addEventListener("mouseleave", function () { popup.classList.add("hidden"); });
    });
  }

  function initAssetsModal() {
    var button = document.getElementById("open-assets-modal");
    var modal = document.getElementById("assets-modal");
    var grid = document.getElementById("assets-grid");
    var status = document.getElementById("assets-modal-status");
    if (!button || !modal || !grid || !status) return;

    function loadAssets(openModal) {
      if (openModal) setModalOpen(modal, true);
      status.classList.remove("hidden");
      status.textContent = "Loading assets…";
      grid.innerHTML = "";
      fetch(button.getAttribute("data-url"), {headers: {"Accept": "application/json"}})
        .then(function (response) {
          if (!response.ok) throw new Error("Could not load product assets");
          return response.json();
        })
        .then(function (data) {
          var assets = data.assets || [];
          if (!assets.length) {
            status.textContent = "No assets have been stored for this product yet.";
            return;
          }
          status.classList.add("hidden");
          grid.innerHTML = assets.map(function (asset, index) {
            return '<div class="relative app-card p-4" data-asset-index="' + index + '">' +
              '<div class="flex items-start justify-between gap-3"><div class="min-w-0">' +
              '<p class="truncate text-sm font-semibold" style="color:var(--color-text)">' + escapeHtml(asset.name) + '</p>' +
              '<p class="mt-1 text-xs uppercase" style="color:var(--color-text-muted)">' + escapeHtml(asset.kind) + ' · ' + formatBytes(asset.size) + '</p>' +
              (asset.is_packed_plate ? '<span class="mt-2 inline-flex rounded-full px-2 py-1 text-xs font-semibold" style="background:var(--color-secondary-soft);color:var(--color-secondary);">Packed Plate</span>' : '') + '</div>' +
              '<div class="flex shrink-0 flex-wrap justify-end gap-1">' +
              (asset.is_pmp_compatible ? '<button type="button" class="app-btn app-btn-primary px-2 py-1 text-xs" data-run-pmp data-pmp-url="' + escapeHtml(asset.pmp_url) + '" data-asset-name="' + escapeHtml(asset.name) + '">Run PMP</button>' : '') +
              '<a class="app-btn app-btn-secondary px-2 py-1 text-xs" href="' + escapeHtml(asset.download_url) + '">Download</a>' +
              '<button type="button" class="app-btn px-2 py-1 text-xs" style="color:var(--color-danger)" data-delete-asset data-delete-url="' + escapeHtml(asset.delete_url) + '" data-asset-name="' + escapeHtml(asset.name) + '" data-deletes-metadata="' + (asset.metadata_will_delete ? 'true' : 'false') + '">Delete</button></div></div>' +
              '</div>';
          }).join("");
          attachAssetMetadataPopups(grid, assets);
        })
        .catch(function (error) { status.textContent = error.message; });
    }
    button.addEventListener("click", function () { loadAssets(true); });
    modal.querySelectorAll("[data-close-assets-modal]").forEach(function (close) {
      close.addEventListener("click", function () { setModalOpen(modal, false); });
    });
    grid.addEventListener("click", function (event) {
      var pmpButton = event.target.closest("[data-run-pmp]");
      if (pmpButton) {
        var sourceName = pmpButton.getAttribute("data-asset-name");
        if (!window.confirm('Run PMP on "' + sourceName + '"? A packed 3MF and JSON metadata file will be saved with this product.')) return;
        pmpButton.disabled = true;
        pmpButton.textContent = "Packing…";
        updateLiveProgress({step: "queued", percent: 2, message: "PMP queued for " + sourceName});
        fetch(pmpButton.getAttribute("data-pmp-url"), {
          method: "POST",
          headers: {"X-CSRFToken": getCSRFToken(), "Accept": "application/json"}
        })
          .then(function (response) {
            return response.json().then(function (data) {
              if (!response.ok) throw new Error(data.error || "Could not start PMP");
              return data;
            });
          })
          .then(function (data) {
            showFlash("PMP started. Progress will update live.", "success");
            pollTask(data.task_id, function (result) {
              if (!result || result.success === false) throw new Error((result && result.error) || "PMP failed");
              updateLiveProgress({step: "complete", percent: 100, message: "Packed plate saved to assets"});
              showFlash("PMP packed " + result.placed + " copies and saved the 3MF to assets.", "success");
              loadAssets(false);
            }, function () {
              showFlash("PMP is still working. Reopen Assets shortly to check the result.", "warning");
              loadAssets(false);
            }, function (progress) { updateLiveProgress(progress, "PMP"); });
          })
          .catch(function (error) {
            showFlash(error.message, "danger");
            pmpButton.disabled = false;
            pmpButton.textContent = "Run PMP";
          });
        return;
      }
      var deleteButton = event.target.closest("[data-delete-asset]");
      if (!deleteButton) return;
      var name = deleteButton.getAttribute("data-asset-name");
      var deletesMetadata = deleteButton.getAttribute("data-deletes-metadata") === "true";
      var message = 'Delete "' + name + '"? This cannot be undone.';
      if (deletesMetadata) {
        message += " The associated JSON metadata file will also be deleted.";
      }
      if (!window.confirm(message)) return;
      deleteButton.disabled = true;
      deleteButton.textContent = "Deleting…";
      fetch(deleteButton.getAttribute("data-delete-url"), {
        method: "DELETE",
        headers: {"X-CSRFToken": getCSRFToken(), "Accept": "application/json"}
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) throw new Error(data.error || "Could not delete asset");
            return data;
          });
        })
        .then(function () {
          showFlash("Asset deleted.", "success");
          loadAssets(false);
        })
        .catch(function (error) {
          showFlash(error.message, "danger");
          deleteButton.disabled = false;
          deleteButton.textContent = "Delete";
        });
    });
  }

  function preventUnhandledFileDrop(e) {
    if (!e.dataTransfer || !e.dataTransfer.types || !Array.prototype.includes.call(e.dataTransfer.types, "Files")) {
      return;
    }
    if (e.target.closest("#model-drop-zone, .image-drop-zone")) {
      return;
    }
    e.preventDefault();
  }

  function updateDropZoneLabel(filename) {
    var label = document.getElementById("drop-zone-label");
    if (label) {
      label.textContent = filename;
    }
  }

  function initReanalyze() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-reanalyze]");
      if (!btn) return;

      var url = btn.getAttribute("data-url");
      if (!url) return;

      btn.disabled = true;
      btn.textContent = "Re-analyzing...";

      fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().then(function (d) {
              throw new Error(d.error || "Re-analysis failed");
            });
          }
          return r.json();
        })
        .then(function (data) {
          showFlash("Re-analysis started.", "success");
          if (data.task_id) {
            pollTask(data.task_id, function () {
              location.reload();
            });
          } else {
            location.reload();
          }
        })
        .catch(function (err) {
          showFlash(err.message || "Re-analysis failed.", "danger");
          btn.disabled = false;
          btn.textContent = "Re-analyze";
        });
    });
  }

  function initCostCalculation() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-calc-costs]");
      if (!btn) return;

      var url = btn.getAttribute("data-url");
      var resultTarget = btn.getAttribute("data-result-target") || "cost-results";
      var productId = btn.getAttribute("data-product-id");
      if (!url || !productId) return;

      btn.disabled = true;
      btn.textContent = "Calculating...";

      var resultEl = document.getElementById(resultTarget);
      if (resultEl) {
        resultEl.innerHTML = '<div class="animate-pulse p-4 text-center text-sm" style="color:var(--color-text-muted);">Calculating costs...</div>';
      }

      fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().then(function (d) {
              throw new Error(d.error || "Request failed");
            });
          }
          return r.json();
        })
        .then(function (data) {
          if (data.task_id) {
            pollTask(data.task_id, function () {
              fetchCostResult(productId, resultTarget, btn);
            }, function () {
              showFlash("Cost calculation timed out. The task may still be running.", "warning");
              resetBtn(btn, "Calculate Cost");
            });
            return;
          }
          showCostResult(data, resultTarget);
          resetBtn(btn, "Re-Calculate");
        })
        .catch(function (err) {
          showFlash(err.message || "Calculation request failed.", "danger");
          resetBtn(btn, "Calculate Cost");
        });
    });
  }

  function fetchCostResult(productId, resultTarget, btn) {
    fetch("/products/studio/cost-result/" + productId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          showCostResult(data, resultTarget);
        }
        resetBtn(btn, "Re-Calculate");
      })
      .catch(function () {
        showFlash("Failed to fetch cost results.", "danger");
        resetBtn(btn, "Calculate Cost");
      });
  }

  function showCostResult(data, targetId) {
    var el = document.getElementById(targetId);
    if (!el) return;
    el.innerHTML =
      '<div class="grid gap-4 md:grid-cols-4">' +
        card("Material Cost", "$" + fmtDecimal(data.material_cost)) +
        card("Total Cost", "$" + fmtDecimal(data.total_cost)) +
        card("Margin", fmtDecimal(data.margin_percent) + "%") +
        card("Print Time", fmtDurationMinutes(data.print_minutes)) +
      '</div>';
  }

  function card(label, value) {
    return (
      '<div class="app-card p-4 text-center">' +
        '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">' + label + '</p>' +
        '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">' + value + '</p>' +
      '</div>'
    );
  }

  function fmtDurationMinutes(value) {
    var totalMinutes = Math.round(Number(value || 0));
    if (!Number.isFinite(totalMinutes) || totalMinutes < 0) totalMinutes = 0;
    var days = Math.floor(totalMinutes / 1440);
    var remainder = totalMinutes % 1440;
    var hours = Math.floor(remainder / 60);
    var minutes = remainder % 60;
    var parts = [];
    if (days > 0) parts.push(days + "d");
    if (hours > 0 || days > 0) parts.push(hours + "h");
    parts.push(minutes + "m");
    return parts.join(" ");
  }

  function fmtDecimal(value) {
    var number = Number(value || 0);
    if (!Number.isFinite(number)) number = 0;
    return number.toFixed(2);
  }

  function resetBtn(btn, text) {
    if (!btn) return;
    btn.disabled = false;
    btn.textContent = text;
  }

  function initImageManagement() {
    document.addEventListener("click", function (e) {
      var zone = e.target.closest(".image-drop-zone");
      if (!zone) return;
      var fileInput = zone.querySelector("[name='image']");
      if (fileInput) fileInput.click();
    });

    document.addEventListener("dragover", function (e) {
      var zone = e.target.closest(".image-drop-zone");
      if (!zone) return;
      e.preventDefault();
      zone.classList.add("border-primary");
    });

    document.addEventListener("dragleave", function (e) {
      var zone = e.target.closest(".image-drop-zone");
      if (!zone) return;
      zone.classList.remove("border-primary");
    });

    document.addEventListener("drop", function (e) {
      var zone = e.target.closest(".image-drop-zone");
      if (!zone) return;
      e.preventDefault();
      zone.classList.remove("border-primary");
      if (e.dataTransfer.files.length) {
        var fileInput = zone.querySelector("[name='image']");
        if (fileInput) {
          fileInput.files = e.dataTransfer.files;
          var label = zone.querySelector("p");
          if (label) label.textContent = e.dataTransfer.files[0].name;
        }
      }
    });

    document.addEventListener("submit", function (e) {
      var form = e.target.closest(".image-upload-form");
      if (!form) return;
      e.preventDefault();

      var productId = form.getAttribute("data-product-id");
      if (!productId) return;

      var formData = new FormData(form);
      var fileInput = form.querySelector("[name='image']");
      if (!fileInput || !fileInput.files.length) {
        showFlash("Please select an image file.", "warning");
        return;
      }

      var btn = form.querySelector("[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Uploading...";
      }

      fetch("/products/studio/" + productId + "/upload-image", {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          return r.ok ? r.json() : r.json().then(function (d) {
            throw new Error(d.error || "Upload failed");
          });
        })
        .then(function () {
          location.reload();
        })
        .catch(function (err) {
          showFlash(err.message || "Upload failed.", "danger");
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Upload Image";
          }
        });
    });

    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".set-default-image");
      if (!btn) return;
      var imageId = btn.getAttribute("data-image-id");
      if (!imageId) return;
      fetch("/products/studio/set-default-image/" + imageId, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          return r.ok ? r.json() : r.json().then(function (d) {
            throw new Error(d.error || "Failed");
          });
        })
        .then(function () { location.reload(); })
        .catch(function (err) { showFlash(err.message || "Failed to set default image.", "danger"); });
    });

    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".set-pos-image");
      if (!btn) return;
      var imageId = btn.getAttribute("data-image-id");
      if (!imageId) return;
      fetch("/products/studio/set-pos-image/" + imageId, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() }
      })
        .then(function (r) {
          return r.ok ? r.json() : r.json().then(function (d) {
            throw new Error(d.error || "Failed");
          });
        })
        .then(function () { location.reload(); })
        .catch(function (err) { showFlash(err.message || "Failed to set POS image.", "danger"); });
    });
  }

  function pollTask(taskId, onComplete, onTimeout, onProgress) {
    var startTime = Date.now();

    function poll() {
      fetch("/products/studio/task-status/" + taskId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.state === "SUCCESS") {
            if (onComplete) onComplete(data.result || data);
            return;
          }
          if (data.state === "FAILURE") {
            showFlash(data.error || "Background task failed.", "danger");
            updateLiveProgress({step: "failed", percent: 100, message: data.error || "Background task failed"});
            return;
          }
          if (onProgress && data.info) onProgress(data.info);
          if (Date.now() - startTime > POLL_TIMEOUT_MS) {
            if (onTimeout) onTimeout();
            return;
          }
          window.setTimeout(poll, 1500);
        })
        .catch(function () {
          if (Date.now() - startTime > POLL_TIMEOUT_MS) {
            if (onTimeout) onTimeout();
            return;
          }
          window.setTimeout(poll, 2000);
        });
    }

    poll();
  }

  function showFlash(message, level) {
    window.dispatchEvent(new CustomEvent("dfpos:flash", { detail: { message: message, category: level } }));
  }
})();
