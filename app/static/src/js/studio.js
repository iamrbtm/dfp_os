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
          showFlash("Model uploaded. Analysis started.", "success");
          if (data.task_id) {
            pollTask(data.task_id, function () {
              location.reload();
            });
          } else {
            location.reload();
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

  function pollTask(taskId, onComplete, onTimeout) {
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
            return;
          }
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
