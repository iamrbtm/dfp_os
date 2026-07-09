/**
 * Dude Fish OS — Theme Switcher
 *
 * Sets data-theme on <html>, persists to localStorage for anonymous
 * users and POSTs to server for authenticated users.
 * Updates Chart.js charts when theme changes.
 */
(function () {
  "use strict";

  var theme = document.documentElement.getAttribute("data-theme");
  if (!theme) {
    theme = localStorage.getItem("dfp-theme") || "dfp-dudefish-light";
    document.documentElement.setAttribute("data-theme", theme);
  }

  function applyTheme(slug) {
    document.documentElement.setAttribute("data-theme", slug);
    localStorage.setItem("dfp-theme", slug);

    updateCharts(slug);

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) {
      fetch("/settings/themes/apply", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfMeta.getAttribute("content"),
        },
        body: JSON.stringify({ theme_slug: slug }),
      }).catch(function () {});
    }
  }

  window.__applyTheme = applyTheme;

  function updateCharts(slug) {
    if (typeof Chart === "undefined") return;
    var root = document.documentElement;
    var style = getComputedStyle(root);
    var colors = [
      style.getPropertyValue("--chart-1").trim() || "#0969da",
      style.getPropertyValue("--chart-2").trim() || "#8250df",
      style.getPropertyValue("--chart-3").trim() || "#1a7f37",
      style.getPropertyValue("--chart-4").trim() || "#9a6700",
      style.getPropertyValue("--chart-5").trim() || "#cf222e",
    ];
    var gridColor = style.getPropertyValue("--chart-grid").trim() || "#d0d7de";
    var axisColor = style.getPropertyValue("--chart-axis").trim() || "#57606a";
    var tooltipBg = style.getPropertyValue("--chart-tooltip-bg").trim() || "#24292f";
    var tooltipText = style.getPropertyValue("--chart-tooltip-text").trim() || "#ffffff";

    Chart.helpers.each(Chart.instances, function (instance) {
      if (instance.options.scales) {
        var scales = instance.options.scales;
        Object.keys(scales).forEach(function (key) {
          if (scales[key].grid) scales[key].grid.color = gridColor;
          if (scales[key].ticks) scales[key].ticks.color = axisColor;
        });
      }
      if (instance.options.plugins && instance.options.plugins.tooltip) {
        instance.options.plugins.tooltip.backgroundColor = tooltipBg;
        instance.options.plugins.tooltip.titleColor = tooltipText;
        instance.options.plugins.tooltip.bodyColor = tooltipText;
      }
      if (instance.data && instance.data.datasets) {
        instance.data.datasets.forEach(function (ds, idx) {
          if (idx < colors.length) {
            ds.borderColor = colors[idx];
            ds.backgroundColor = colors[idx] + "33";
          }
        });
      }
      instance.update("none");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.documentElement;
    var saved = localStorage.getItem("dfp-theme");
    if (saved && saved !== root.getAttribute("data-theme")) {
      root.setAttribute("data-theme", saved);
    }
  });
})();
