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
    initVariantModelUpload();
    initVariantForm();
    initCostCalculation();
    initReanalyze();
    initImageManagement();
    initFileRename();
  });

  function initModelUpload() {
    var dropZone = document.getElementById("model-drop-zone");
    var fileInput = document.getElementById("model_file");
    var uploadForm = document.getElementById("model-upload-form");

    if (!dropZone || !fileInput || !uploadForm) return;
    var productId = uploadForm.getAttribute("data-product-id");
    if (!productId) return;

    dropZone.addEventListener("click", function () {
      fileInput.click();
    });

    dropZone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropZone.classList.add("border-primary");
    });

    dropZone.addEventListener("dragleave", function () {
      dropZone.classList.remove("border-primary");
    });

    dropZone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropZone.classList.remove("border-primary");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        updateDropZoneLabel(e.dataTransfer.files[0].name);
      }
    });

    fileInput.addEventListener("change", function () {
      if (fileInput.files.length) {
        updateDropZoneLabel(fileInput.files[0].name);
      }
    });

    uploadForm.addEventListener("submit", function (e) {
      e.preventDefault();

      var formData = new FormData(uploadForm);
      var csrfToken = getCSRFToken();

      var btn = uploadForm.querySelector("[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Uploading...";
      }

      fetch("/products/studio/" + productId + "/upload-model", {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": csrfToken,
        },
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (d) {
            throw new Error(d.error || "Upload failed");
          });
          return r.json();
        })
        .then(function (data) {
          showFlash("Model uploaded. Analysis started.", "success");
          if (data.task_id) {
            pollTask(data.task_id, function () {
              showFlash("Model analysis complete!", "success");
              location.reload();
            });
          }
        })
        .catch(function (err) {
          showFlash(err.message || "Upload failed.", "danger");
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Upload & Analyze";
          }
        });
    });
  }

  function initVariantModelUpload() {
    document.addEventListener("click", function (e) {
      var zone = e.target.closest(".variant-drop-zone");
      if (!zone) return;
      var fileInput = zone.querySelector("[name='model_file']");
      if (fileInput) fileInput.click();
    });

    document.addEventListener("dragover", function (e) {
      var zone = e.target.closest(".variant-drop-zone");
      if (!zone) return;
      e.preventDefault();
      zone.classList.add("border-primary");
    });

    document.addEventListener("dragleave", function (e) {
      var zone = e.target.closest(".variant-drop-zone");
      if (!zone) return;
      zone.classList.remove("border-primary");
    });

    document.addEventListener("drop", function (e) {
      var zone = e.target.closest(".variant-drop-zone");
      if (!zone) return;
      e.preventDefault();
      zone.classList.remove("border-primary");
      if (e.dataTransfer.files.length) {
        var fileInput = zone.querySelector("[name='model_file']");
        if (fileInput) {
          fileInput.files = e.dataTransfer.files;
          var label = zone.querySelector("p");
          if (label) label.textContent = e.dataTransfer.files[0].name;
        }
      }
    });

    document.addEventListener("change", function (e) {
      if (e.target.matches(".variant-drop-zone [name='model_file']")) {
        var zone = e.target.closest(".variant-drop-zone");
        if (zone && e.target.files.length) {
          var label = zone.querySelector("p");
          if (label) label.textContent = e.target.files[0].name;
        }
      }
    });

    document.addEventListener("submit", function (e) {
      var form = e.target.closest(".variant-model-upload-form");
      if (!form) return;

      e.preventDefault();

      var variantId = form.getAttribute("data-variant-id");
      var productId = form.getAttribute("data-product-id");
      if (!variantId || !productId) return;

      var fileInput = form.querySelector("[name='model_file']");
      if (!fileInput || !fileInput.files.length) {
        showFlash("Please select a model file.", "warning");
        return;
      }

      var formData = new FormData(form);
      var csrfToken = getCSRFToken();

      var btn = form.querySelector("[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Uploading...";
      }

      fetch("/products/studio/" + productId + "/upload-model", {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": csrfToken,
        },
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (d) {
            throw new Error(d.error || "Upload failed");
          });
          return r.json();
        })
        .then(function (data) {
          showFlash("Variant model uploaded. Analysis started.", "success");
          if (data.task_id) {
            pollTask(data.task_id, function () {
              showFlash("Variant model analysis complete!", "success");
              location.reload();
            });
          }
        })
        .catch(function (err) {
          showFlash(err.message || "Upload failed.", "danger");
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Upload for Variant";
          }
        });
    });
  }

  function updateDropZoneLabel(filename) {
    const label = document.getElementById("drop-zone-label");
    if (label) {
      label.textContent = filename;
      label.classList.add("text-sm", "font-medium");
    }
  }

  function initReanalyze() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-reanalyze]");
      if (!btn) return;

      var url = btn.getAttribute("data-url");
      var assetId = btn.getAttribute("data-asset-id");
      if (!url || !assetId) return;

      btn.disabled = true;
      btn.textContent = "Re-analyzing...";

      fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
        },
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (d) {
            throw new Error(d.error || "Re-analysis failed");
          });
          return r.json();
        })
        .then(function (data) {
          showFlash("Re-analysis started.", "success");
          if (data.task_id) {
            pollTask(data.task_id, function () {
              showFlash("Model re-analysis complete!", "success");
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

  function initVariantForm() {
    const addBtn = document.getElementById("add-variant-btn");
    const form = document.getElementById("variant-form");
    if (!addBtn || !form) return;
    var productId = form.getAttribute("data-product-id");
    if (!productId) return;

    addBtn.addEventListener("click", function () {
      form.classList.remove("hidden");
      addBtn.classList.add("hidden");
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();

      const sku = form.querySelector("[name='sku']");
      const name = form.querySelector("[name='name']");
      if (!sku.value || !name.value) {
        showFlash("SKU and Name are required.", "warning");
        return;
      }

      var btn = form.querySelector("[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Saving...";
      }

      fetch("/products/studio/create-variant/" + productId, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-CSRFToken": getCSRFToken(),
        },
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (d) {
            throw new Error(d.error || "Failed to add variant");
          });
          return r.json();
        })
        .then(function (resp) {
          if (!resp.success) {
            throw new Error(resp.error || "Failed to add variant");
          }
          showFlash("Variant added.", "success");
          location.reload();
        })
        .catch(function (err) {
          showFlash(err.message || "Failed to add variant.", "danger");
        })
        .finally(function () {
          if (btn) {
            btn.disabled = false;
            btn.textContent = "Save Variant";
          }
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
      var variantId = btn.getAttribute("data-variant-id");

      if (!url) return;

      btn.disabled = true;
      btn.textContent = "Calculating...";

      var resultEl = document.getElementById(resultTarget);
      if (resultEl) {
        resultEl.innerHTML =
          '<div class="animate-pulse p-4 text-center text-sm" style="color:var(--color-text-muted);">Calculating costs...</div>';
      }

      fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
        },
      })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (d) {
            throw new Error(d.error || "Request failed");
          });
          return r.json();
        })
        .then(function (data) {
          if (data.task_id) {
            pollTask(data.task_id, function (taskResult) {
              if (productId) {
                fetchCostResult(productId, resultTarget, btn);
              } else if (variantId) {
                showCostResult(taskResult || data, resultTarget);
                resetBtn(btn, "Re-Calculate");
              }
            }, function () {
              showFlash("Cost calculation timed out. The task may still be running.", "warning");
              resetBtn(btn, "Retry Calculate");
            });
          } else if (data.success) {
            showCostResult(data, resultTarget);
            resetBtn(btn, "Re-Calculate");
          } else {
            showFlash(data.error || "Calculation failed.", "danger");
            resetBtn(btn, "Calculate Costs");
          }
        })
        .catch(function (err) {
          showFlash(err.message || "Calculation request failed.", "danger");
          resetBtn(btn, "Calculate Costs");
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
        resetBtn(btn, "Calculate Costs");
      });
  }

  function showCostResult(data, targetId) {
    var el = document.getElementById(targetId);
    if (!el) return;
    if (data && data.variant_id) {
      el.innerHTML =
        '<div class="grid gap-4 md:grid-cols-3">' +
          '<div class="app-card p-4 text-center">' +
            '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Material Cost</p>' +
            '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">$' + fmtDecimal(data.material_cost) + '</p>' +
          '</div>' +
          '<div class="app-card p-4 text-center">' +
            '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Filament</p>' +
            '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">' + fmtDecimal(data.filament_grams) + ' g</p>' +
          '</div>' +
          '<div class="app-card p-4 text-center">' +
            '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Print Time</p>' +
            '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">' + fmtDecimal(data.print_minutes) + ' min</p>' +
          '</div>' +
        '</div>';
      return;
    }
    el.innerHTML =
      '<div class="grid gap-4 md:grid-cols-3">' +
        '<div class="app-card p-4 text-center">' +
          '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Material Cost</p>' +
          '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">$' + fmtDecimal(data.material_cost) + '</p>' +
        '</div>' +
        '<div class="app-card p-4 text-center">' +
          '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Total Cost</p>' +
          '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">$' + fmtDecimal(data.total_cost) + '</p>' +
        '</div>' +
        '<div class="app-card p-4 text-center">' +
          '<p class="text-xs uppercase tracking-wider" style="color:var(--color-text-muted);">Margin</p>' +
          '<p class="text-2xl font-bold mt-1" style="color:var(--color-text);">' + fmtDecimal(data.margin_percent) + '%</p>' +
        '</div>' +
      '</div>';
  }

  function initFileRename() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".file-rename-btn");
      if (!btn) return;
      var row = btn.closest("[data-file-id]");
      if (!row) return;
      var titleEl = row.querySelector(".file-title");
      var inputEl = row.querySelector(".file-title-input");
      if (!titleEl || !inputEl) return;

      var isEditing = !inputEl.classList.contains("hidden");
      if (isEditing) {
        cancelRename(row, titleEl, inputEl);
        return;
      }

      titleEl.classList.add("hidden");
      inputEl.classList.remove("hidden");
      inputEl.focus();
      inputEl.select();
    });

    document.addEventListener("keydown", function (e) {
      var input = e.target.closest(".file-title-input:not(.hidden)");
      if (!input) return;
      var row = input.closest("[data-file-id]");
      if (!row) return;

      if (e.key === "Enter") {
        e.preventDefault();
        submitRename(row, input);
      } else if (e.key === "Escape") {
        e.preventDefault();
        var titleEl = row.querySelector(".file-title");
        cancelRename(row, titleEl, input);
      }
    });

    document.addEventListener("blur", function (e) {
      var input = e.target.closest(".file-title-input:not(.hidden)");
      if (!input) return;
      var row = input.closest("[data-file-id]");
      if (!row) return;
      submitRename(row, input);
    }, true);

    function submitRename(row, input) {
      var newTitle = input.value.trim();
      var oldTitle = row.querySelector(".file-title");
      if (!newTitle || newTitle === (oldTitle ? oldTitle.textContent.trim() : "")) {
        cancelRename(row, oldTitle, input);
        return;
      }

      var fileId = row.getAttribute("data-file-id");
      var fileType = row.getAttribute("data-file-type");
      if (!fileId || !fileType) {
        cancelRename(row, oldTitle, input);
        return;
      }

      fetch("/products/studio/rename-file", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ id: parseInt(fileId, 10), type: fileType, title: newTitle }),
      })
        .then(function (r) { return r.ok ? r.json() : r.json().then(function (d) { throw new Error(d.error || "Rename failed"); }); })
        .then(function () {
          if (oldTitle) oldTitle.textContent = newTitle;
          cancelRename(row, oldTitle, input);
          showFlash("Renamed.", "success");
        })
        .catch(function (err) {
          cancelRename(row, oldTitle, input);
          showFlash(err.message || "Rename failed.", "danger");
        });
    }

    function cancelRename(row, titleEl, inputEl) {
      if (titleEl) titleEl.classList.remove("hidden");
      if (inputEl) {
        inputEl.classList.add("hidden");
        inputEl.value = titleEl ? titleEl.textContent.trim() : inputEl.value;
      }
    }
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
      if (btn) { btn.disabled = true; btn.textContent = "Uploading..."; }

      fetch("/products/studio/" + productId + "/upload-image", {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": getCSRFToken() },
      })
        .then(function (r) { return r.ok ? r.json() : r.json().then(function (d) { throw new Error(d.error || "Upload failed"); }); })
        .then(function (data) {
          showFlash("Image uploaded.", "success");
          location.reload();
        })
        .catch(function (err) { showFlash(err.message || "Upload failed.", "danger"); })
        .finally(function () { if (btn) { btn.disabled = false; btn.textContent = "Upload Image"; } });
    });

    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".set-default-image");
      if (!btn) return;
      var imageId = btn.getAttribute("data-image-id");
      if (!imageId) return;
      fetch("/products/studio/set-default-image/" + imageId, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() },
      })
        .then(function (r) { return r.ok ? r.json() : r.json().then(function (d) { throw new Error(d.error || "Failed"); }); })
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
        headers: { "X-CSRFToken": getCSRFToken() },
      })
        .then(function (r) { return r.ok ? r.json() : r.json().then(function (d) { throw new Error(d.error || "Failed"); }); })
        .then(function () { location.reload(); })
        .catch(function (err) { showFlash(err.message || "Failed to set POS image.", "danger"); });
    });
  }

  function pollTask(taskId, onComplete, onTimeout) {
    var startTime = Date.now();
    var timedOut = false;
    var interval = setInterval(function () {
      if (Date.now() - startTime > POLL_TIMEOUT_MS) {
        clearInterval(interval);
        if (!timedOut) {
          timedOut = true;
          if (onTimeout) onTimeout();
        }
        return;
      }

      fetch("/products/studio/task-status/" + taskId)
        .then(function (r) {
          if (!r.ok) throw new Error("Status check failed (" + r.status + ")");
          return r.json();
        })
        .then(function (data) {
          if (timedOut) return;
          if (data.state === "SUCCESS") {
            clearInterval(interval);
            if (onComplete) onComplete(data.result);
          } else if (data.state === "FAILURE") {
            clearInterval(interval);
            showFlash(data.error || "Task failed.", "danger");
          }
        })
        .catch(function (err) {
          if (timedOut) return;
          showFlash("Polling error: " + (err.message || "connection failed"), "warning");
          clearInterval(interval);
        });
    }, 1500);
  }

  function resetBtn(btn, text) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = text || "Calculate Costs";
    }
  }

  function fmtDecimal(val) {
    if (val == null || val === undefined) return "0.00";
    var n = parseFloat(val);
    if (isNaN(n)) return "0.00";
    return n.toFixed(2);
  }

  function showFlash(msg, category) {
    var container = document.getElementById("flash-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "flash-container";
      container.className = "fixed top-4 right-4 z-50 max-w-sm space-y-2";
      document.body.appendChild(container);
    }
    var div = document.createElement("div");
    div.className =
      "app-alert app-alert-" +
      (category || "info") +
      " p-4 rounded-lg shadow-lg";
    var colors = {
      success: "var(--color-success)",
      danger: "var(--color-danger)",
      warning: "var(--color-warning)",
      info: "var(--color-info)",
    };
    div.style.backgroundColor = colors[category] || colors.info;
    div.style.color = "#fff";
    div.textContent = msg;
    container.appendChild(div);
    setTimeout(function () {
      div.style.opacity = "0";
      div.style.transition = "opacity 0.3s";
      setTimeout(function () {
        if (div.parentNode) div.parentNode.removeChild(div);
      }, 300);
    }, 4000);
  }
})();
