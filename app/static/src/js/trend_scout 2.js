(function () {
  'use strict';

  var STORAGE_KEY = 'ts_saved_view';
  var MATRIX = document.getElementById('opportunity-matrix');
  if (!MATRIX) return;

  var TBODY = MATRIX.querySelector('tbody');
  var ALL_ROWS = Array.from(TBODY.querySelectorAll('tr'));
  var DATA_ROWS = ALL_ROWS.filter(function (r) { return r.id && r.id.indexOf('detail-') !== 0; });
  var SORT_STATE = { col: null, asc: true };
  var ACTIVE_VIEW = 'all';

  function getRowData(row) {
    var cells = row.querySelectorAll('td');
    return {
      rank: parseFloat(cells[1]?.textContent.trim()) || 0,
      score: parseFloat(cells[4]?.textContent.trim()) || 0,
      intent: parseFloat(cells[5]?.textContent.trim()) || 0,
      velocity: parseFloat(cells[6]?.textContent.trim()) || 0,
      price: parseFloat(cells[7]?.textContent.trim()) || 0,
      lowSat: parseFloat(cells[8]?.textContent.trim()) || 0,
      local: parseFloat(cells[9]?.textContent.trim()) || 0,
      prod: parseFloat(cells[10]?.textContent.trim()) || 0,
      license: parseFloat(cells[11]?.textContent.trim()) || 0,
      inventory: parseFloat(cells[12]?.textContent.trim()) || 0,
      action: cells[3]?.textContent.trim().toLowerCase().replace(/\s+/g, '_') || '',
    };
  }

  function matchesView(rowData, view) {
    if (view === 'all') return true;
    return rowData.action === view;
  }

  function matchesSearch(rowData, query) {
    if (!query) return true;
    var q = query.toLowerCase();
    var text = (row.querySelector('td:nth-child(3)')?.textContent || '').toLowerCase();
    return text.indexOf(q) !== -1;
  }

  function matchesFilter(rowData, filterAction, filterType) {
    if (filterAction && filterAction !== 'all' && rowData.action !== filterAction) return false;
    if (filterType === 'current' && row.querySelector('td:nth-child(3)')?.textContent.indexOf('Current product') === -1) return false;
    if (filterType === 'potential' && row.querySelector('td:nth-child(3)')?.textContent.indexOf('Potential product') === -1) return false;
    return true;
  }

  function saveView() {
    var state = {
      view: ACTIVE_VIEW,
      search: document.getElementById('ts-search')?.value || '',
      filterAction: document.getElementById('ts-filter-action')?.value || 'all',
      filterType: document.getElementById('ts-filter-type')?.value || 'all',
      sortCol: SORT_STATE.col,
      sortAsc: SORT_STATE.asc,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      var btn = document.getElementById('ts-save-view');
      if (btn) {
        btn.textContent = 'Saved!';
        setTimeout(function () { btn.textContent = 'Save View'; }, 2000);
      }
    } catch (e) {}
  }

  function restoreView() {
    var raw;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (e) { return; }
    if (!raw) return;
    var state;
    try { state = JSON.parse(raw); } catch (e) { return; }
    if (!state) return;

    if (state.view) setView(state.view);
    if (state.search) {
      var el = document.getElementById('ts-search');
      if (el) el.value = state.search;
    }
    if (state.filterAction) {
      var el = document.getElementById('ts-filter-action');
      if (el) el.value = state.filterAction;
    }
    if (state.filterType) {
      var el = document.getElementById('ts-filter-type');
      if (el) el.value = state.filterType;
    }
    if (state.sortCol !== null && state.sortCol !== undefined) {
      SORT_STATE.col = state.sortCol;
      SORT_STATE.asc = state.sortAsc !== false;
      var th = MATRIX.querySelector('th[data-sort="' + state.sortCol + '"]');
      if (th) {
        document.querySelectorAll('[data-sort]').forEach(function (h) {
          h.textContent = h.textContent.replace(/ [▲▼]$/, '');
        });
        th.textContent += SORT_STATE.asc ? ' ▲' : ' ▼';
      }
    }
    applyFiltersAndSort();
  }

  function applyFiltersAndSort() {
    var q = (document.getElementById('ts-search')?.value || '').toLowerCase();
    var filterAction = document.getElementById('ts-filter-action')?.value || 'all';
    var filterType = document.getElementById('ts-filter-type')?.value || 'all';

    var visible = DATA_ROWS.filter(function (row) {
      var data = getRowData(row);
      if (!matchesView(data, ACTIVE_VIEW)) return false;
      var nameText = (row.querySelector('td:nth-child(3)')?.textContent || '').toLowerCase();
      if (q && nameText.indexOf(q) === -1) return false;
      if (filterAction !== 'all' && data.action !== filterAction) return false;
      if (filterType === 'current' && nameText.indexOf('current product') === -1) return false;
      if (filterType === 'potential' && nameText.indexOf('potential product') === -1) return false;
      return true;
    });

    var col = SORT_STATE.col;
    if (col !== null) {
      visible.sort(function (a, b) {
        var aData = getRowData(a);
        var bData = getRowData(b);
        var keys = ['score', 'intent', 'velocity', 'price', 'lowSat', 'local', 'prod', 'license', 'inventory', 'rank'];
        var key = keys[col - 4] || 'score';
        var av = aData[key] || 0;
        var bv = bData[key] || 0;
        return SORT_STATE.asc ? av - bv : bv - av;
      });
    }

    var detailRows = [];
    visible.forEach(function (row) {
      var detail = document.getElementById('detail-' + (getRowData(row).rank || row.rowIndex));
      if (detail) detailRows.push(detail);
    });

    ALL_ROWS.forEach(function (r) { r.style.display = 'none'; });
    visible.forEach(function (r) {
      r.style.display = '';
      var rank = getRowData(r).rank || r.rowIndex;
      var detail = document.getElementById('detail-' + rank);
      if (detail && !detail.classList.contains('hidden')) detail.style.display = '';
    });
  }

  function setView(view) {
    ACTIVE_VIEW = view;
    document.querySelectorAll('.ts-view-pill').forEach(function (pill) {
      var v = pill.getAttribute('data-view') || 'all';
      if (v === view) {
        pill.style.opacity = '1';
        pill.style.fontWeight = '700';
      } else {
        pill.style.opacity = '0.6';
        pill.style.fontWeight = '400';
      }
    });
    applyFiltersAndSort();
  }

  document.querySelectorAll('[data-sort]').forEach(function (th) {
    th.style.cursor = 'pointer';
    th.addEventListener('click', function () {
      var col = parseInt(th.getAttribute('data-sort'), 10);
      if (SORT_STATE.col === col) {
        SORT_STATE.asc = !SORT_STATE.asc;
      } else {
        SORT_STATE.col = col;
        SORT_STATE.asc = false;
      }
      document.querySelectorAll('[data-sort]').forEach(function (h) {
        h.textContent = h.textContent.replace(/ [▲▼]$/, '');
      });
      th.textContent += SORT_STATE.asc ? ' ▲' : ' ▼';
      applyFiltersAndSort();
    });
  });

  document.querySelectorAll('.ts-view-pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      setView(pill.getAttribute('data-view') || 'all');
    });
  });

  document.getElementById('ts-search')?.addEventListener('input', applyFiltersAndSort);
  document.getElementById('ts-filter-action')?.addEventListener('change', applyFiltersAndSort);
  document.getElementById('ts-filter-type')?.addEventListener('change', applyFiltersAndSort);
  document.getElementById('ts-save-view')?.addEventListener('click', saveView);

  restoreView();

})();
