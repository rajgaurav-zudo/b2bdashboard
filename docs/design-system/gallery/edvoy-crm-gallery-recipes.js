/**
 * Edvoy CRM Design System v1.0.0 — interaction recipes
 *
 * Reference behaviour for the ARIA contract in css/edvoy-crm-components.css.
 * Plain ES5, no dependencies. Consumers may load this file or implement the
 * same contract themselves. ONE implementation per pattern lives here; the
 * gallery page adds only demo data/policy on top.
 *
 *   EcrmRecipes.initRadioGroup(el)      [role=radiogroup] roving focus, arrows, Home/End, click
 *   EcrmRecipes.initListbox(el)         [role=listbox] single/multi, roving focus, Space/Enter
 *   EcrmRecipes.initPressGroup(el)      [data-ecrm-press] single-select aria-pressed group
 *   EcrmRecipes.initCurrentGroup(el)    [data-ecrm-current] demo aria-current switching
 *   EcrmRecipes.initHierarchy(table)    .ecrm-expand[aria-controls] row disclosure
 *   EcrmRecipes.initSortable(table)     th[data-ecrm-col] .ecrm-sort truthful sorting
 *   EcrmRecipes.Drawer.open/close       modal drawer: inert, focus entry/trap/return, Escape
 *   disabled guard                      [aria-disabled=true] resists pointer + keyboard
 *
 * Every state change dispatches a bubbling "ecrm-change" CustomEvent from the
 * container with { detail: { item } } so consumers attach business logic.
 * None of these recipes scrolls the page (selection changes focus, not location).
 */
/* eslint-env browser */
(function (global) {
  'use strict';
  var A = Array.prototype;
  function attr(el, n) { return el.getAttribute(n); }
  function isDisabled(el) { return attr(el, 'aria-disabled') === 'true' || el.disabled === true; }
  function emit(el, item) {
    var ev; try { ev = new CustomEvent('ecrm-change', { bubbles: true, detail: { item: item } }); }
    catch (e) { ev = document.createEvent('CustomEvent'); ev.initCustomEvent('ecrm-change', true, false, { item: item }); }
    el.dispatchEvent(ev);
  }
  function focusNoScroll(el) { try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); } }

  // ─── Disabled guard ─────────────────────────────────────────────────────
  // aria-disabled controls stay focusable (so their title/reason is reachable)
  // but never activate. Capture phase so no other handler sees the event.
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[aria-disabled="true"]');
    if (el) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var el = e.target.closest && e.target.closest('[aria-disabled="true"]');
    if (el) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);

  // ─── Radio group (roving tabindex; selection follows focus) ─────────────
  function initRadioGroup(group) {
    var all = A.slice.call(group.querySelectorAll('[role="radio"]'));
    if (!all.length) return;
    function enabled() { return all.filter(function (x) { return !isDisabled(x); }); }
    function select(item, focus) {
      all.forEach(function (x) { var on = x === item; x.setAttribute('aria-checked', String(on)); x.setAttribute('tabindex', on ? '0' : '-1'); });
      if (focus) focusNoScroll(item);
      emit(group, item);
    }
    var cur = all.filter(function (x) { return attr(x, 'aria-checked') === 'true'; })[0] || enabled()[0];
    all.forEach(function (x) { x.setAttribute('tabindex', x === cur ? '0' : '-1'); });
    group.addEventListener('click', function (e) {
      var item = e.target.closest('[role="radio"]');
      if (item && all.indexOf(item) > -1 && !isDisabled(item)) select(item, false);
    });
    group.addEventListener('keydown', function (e) {
      var items = enabled(), idx = items.indexOf(document.activeElement), next = -1;
      if (idx < 0) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % items.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + items.length) % items.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = items.length - 1;
      else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); select(items[idx], false); return; }
      if (next < 0) return;
      e.preventDefault(); select(items[next], true);
    });
  }

  // ─── Listbox (focus moves with arrows; Space/Enter/click selects) ───────
  function initListbox(lb) {
    var opts = A.slice.call(lb.querySelectorAll('[role="option"]'));
    if (!opts.length) return;
    var multi = attr(lb, 'aria-multiselectable') === 'true';
    function rove(o) { opts.forEach(function (x) { x.setAttribute('tabindex', x === o ? '0' : '-1'); }); }
    function choose(o) {
      if (isDisabled(o)) return;
      if (multi) o.setAttribute('aria-selected', String(attr(o, 'aria-selected') !== 'true'));
      else opts.forEach(function (x) { x.setAttribute('aria-selected', String(x === o)); });
      rove(o); emit(lb, o);
    }
    rove(opts.filter(function (x) { return attr(x, 'aria-selected') === 'true'; })[0] || opts[0]);
    lb.addEventListener('click', function (e) { var o = e.target.closest('[role="option"]'); if (o && opts.indexOf(o) > -1) choose(o); });
    lb.addEventListener('keydown', function (e) {
      var idx = opts.indexOf(document.activeElement), next = -1;
      if (idx < 0) return;
      if (e.key === 'ArrowDown') next = Math.min(idx + 1, opts.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(idx - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = opts.length - 1;
      else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); choose(opts[idx]); return; }
      if (next < 0) return;
      e.preventDefault(); rove(opts[next]); focusNoScroll(opts[next]);
    });
  }

  // ─── Single-select press group (KPI strip, findings, evidence, bars, chips)
  // Container: data-ecrm-press="single" (one or none pressed) or "single-required".
  // Items: <button aria-pressed>. Optional host: item.closest('[data-ecrm-selectable]')
  // receives .is-selected (used by evidence cards whose heading is the button).
  function initPressGroup(group) {
    var mode = attr(group, 'data-ecrm-press');
    function items() { return A.filter.call(group.querySelectorAll('[aria-pressed]'), function (x) { return x.closest('[data-ecrm-press]') === group; }); }
    function sync() { items().forEach(function (x) { var h = x.closest('[data-ecrm-selectable]'); if (h && group.contains(h)) h.classList.toggle('is-selected', attr(x, 'aria-pressed') === 'true'); }); }
    group.addEventListener('click', function (e) {
      var b = e.target.closest('[aria-pressed]');
      if (!b || b.closest('[data-ecrm-press]') !== group || isDisabled(b)) return;
      var was = attr(b, 'aria-pressed') === 'true';
      if (was && mode === 'single-required') return;
      items().forEach(function (x) { x.setAttribute('aria-pressed', String(x === b ? !was : false)); });
      sync(); emit(group, b);
    });
    sync();
  }

  // ─── aria-current group (demo only: real navigation changes location) ───
  function initCurrentGroup(group) {
    group.addEventListener('click', function (e) {
      var b = e.target.closest('a,button');
      if (!b || !group.contains(b) || isDisabled(b)) return;
      if (b.tagName === 'A' && attr(b, 'href') === '#') e.preventDefault();
      A.forEach.call(group.querySelectorAll('a,button'), function (x) { if (x === b) x.setAttribute('aria-current', 'page'); else x.removeAttribute('aria-current'); });
      emit(group, b);
    });
  }

  // ─── Hierarchy rows ─────────────────────────────────────────────────────
  // .ecrm-expand[aria-controls="id id"][data-ecrm-name] toggles [hidden] on the
  // controlled rows, aria-expanded and the accessible name. Collapsing a parent
  // also collapses expanded descendants.
  function setExpanded(btn, open, table) {
    btn.setAttribute('aria-expanded', String(open));
    var name = attr(btn, 'data-ecrm-name') || '';
    btn.setAttribute('aria-label', (open ? 'Collapse ' : 'Expand ') + name);
    (attr(btn, 'aria-controls') || '').split(/\s+/).forEach(function (id) {
      var row = id && document.getElementById(id); if (!row) return;
      row.hidden = !open;
      if (!open) { var inner = row.querySelector('.ecrm-expand[aria-expanded="true"]'); if (inner) setExpanded(inner, false, table); }
    });
  }
  function initHierarchy(table) {
    A.forEach.call(table.querySelectorAll('.ecrm-expand[aria-controls]'), function (b) { setExpanded(b, attr(b, 'aria-expanded') === 'true', table); });
    table.addEventListener('click', function (e) {
      var b = e.target.closest('.ecrm-expand[aria-controls]'); if (!b) return;
      setExpanded(b, attr(b, 'aria-expanded') !== 'true', table); emit(table, b);
    });
  }

  // ─── Sortable table (truthful) ──────────────────────────────────────────
  // th[data-ecrm-col=N] contains button.ecrm-sort. Rows with [data-ecrm-pin]
  // stay first. Rows with [data-ecrm-child-of] travel with their parent
  // (tr[data-ecrm-row]) and are not reordered among themselves. Missing values
  // ("—", empty) always sort last. Announces via an optional
  // [data-ecrm-sort-status] element referenced by the table's data attribute.
  // Returns a number, a string (text columns) or null (missing: .ecrm-missing / empty).
  function cellKey(row, col) {
    var c = row.cells[col]; if (!c || c.querySelector('.ecrm-missing')) return null;
    var v = c.querySelector('.ecrm-cell-value') || c.querySelector('.ecrm-table__name') || c;
    var raw = (v.textContent || '').trim(); if (!raw || raw === '—') return null;
    var n = parseFloat(raw.replace(/[,\s]/g, '').replace('−', '-'));
    return isNaN(n) ? raw.toLowerCase() : n;
  }
  function initSortable(table) {
    var body = table.tBodies[0]; if (!body) return;
    var status = table.id && document.querySelector('[data-ecrm-sort-status="' + table.id + '"]');
    A.forEach.call(table.querySelectorAll('th[data-ecrm-col] .ecrm-sort'), function (btn) {
      btn.addEventListener('click', function () {
        var th = btn.closest('th'), col = parseInt(attr(th, 'data-ecrm-col'), 10);
        var dir = attr(th, 'aria-sort') === 'descending' ? 'ascending' : 'descending';
        A.forEach.call(table.querySelectorAll('th[data-ecrm-col]'), function (h) { h.setAttribute('aria-sort', h === th ? dir : 'none'); });
        var rows = A.slice.call(body.rows), pinned = [], groups = [], byId = {};
        rows.forEach(function (r) {
          if (r.hasAttribute('data-ecrm-pin')) pinned.push(r);
          else if (r.hasAttribute('data-ecrm-child-of')) { var g = byId[attr(r, 'data-ecrm-child-of')]; if (g) g.kids.push(r); else groups.push({ head: r, kids: [] }); }
          else { var grp = { head: r, kids: [] }; groups.push(grp); if (attr(r, 'data-ecrm-row')) byId[attr(r, 'data-ecrm-row')] = grp; }
        });
        groups.sort(function (a, b) {
          var x = cellKey(a.head, col), y = cellKey(b.head, col);
          if (x === null && y === null) return 0; if (x === null) return 1; if (y === null) return -1;
          var d = (typeof x === 'number' && typeof y === 'number') ? x - y : String(x).localeCompare(String(y));
          return dir === 'ascending' ? d : -d;
        });
        pinned.forEach(function (r) { body.appendChild(r); });
        groups.forEach(function (g) { body.appendChild(g.head); g.kids.forEach(function (k) { body.appendChild(k); }); });
        if (status) status.textContent = 'Sorted by ' + btn.textContent.trim() + ', ' + dir + '.';
        emit(table, th);
      });
    });
  }

  // ─── Modal drawer ───────────────────────────────────────────────────────
  // Markup: <div class="ecrm-drawer-scrim" hidden></div>
  //         <div class="ecrm-drawer" role="dialog" aria-modal="true"
  //              aria-labelledby="…" hidden> … <h2 tabindex="-1"> … </div>
  // Both must be direct children of <body> (everything else becomes inert).
  // Closing controls: any [data-ecrm-drawer-close] inside, Escape, scrim click.
  // The drawer emits "ecrm-drawer-close" with detail.reason so the consumer
  // decides what close means (e.g. discard a draft). Apply/Reset are consumer policy.
  var Drawer = {
    _open: null,
    _focusables: function (d) {
      return A.filter.call(d.querySelectorAll('button,[href],input,select,textarea,summary,[tabindex]'), function (x) {
        return !x.disabled && attr(x, 'tabindex') !== '-1' && !x.closest('[hidden]') && x.getClientRects().length > 0;
      });
    },
    open: function (drawer, trigger) {
      if (!drawer || this._open) return;
      var scrim = drawer.previousElementSibling && drawer.previousElementSibling.classList.contains('ecrm-drawer-scrim') ? drawer.previousElementSibling : null;
      var state = { drawer: drawer, scrim: scrim, trigger: trigger || document.activeElement, inert: [] };
      A.forEach.call(document.body.children, function (el) {
        if (el === drawer || el === scrim || el.tagName === 'SCRIPT') return;
        state.inert.push({ el: el, was: el.hasAttribute('inert') });
        el.setAttribute('inert', '');
      });
      if (scrim) scrim.hidden = false;
      drawer.hidden = false;
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
      this._open = state;
      var title = drawer.querySelector('#' + attr(drawer, 'aria-labelledby')) || drawer;
      if (!title.hasAttribute('tabindex')) title.setAttribute('tabindex', '-1');
      focusNoScroll(title);
      var self = this;
      state.onKey = function (e) {
        if (e.key === 'Escape') { if (e.defaultPrevented) return; e.preventDefault(); self.close('escape'); return; }
        if (e.key !== 'Tab') return;
        var f = self._focusables(drawer); if (!f.length) { e.preventDefault(); return; }
        var i = f.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); focusNoScroll(f[f.length - 1]); }
        else if (!e.shiftKey && (i === -1 || i === f.length - 1)) { e.preventDefault(); focusNoScroll(f[0]); }
      };
      state.onClick = function (e) { var c = e.target.closest('[data-ecrm-drawer-close]'); if (c && drawer.contains(c)) self.close(attr(c, 'data-ecrm-drawer-close') || 'close'); };
      state.onScrim = function () { self.close('scrim'); };
      document.addEventListener('keydown', state.onKey);
      drawer.addEventListener('click', state.onClick);
      if (scrim) scrim.addEventListener('click', state.onScrim);
    },
    close: function (reason) {
      var s = this._open; if (!s) return;
      document.removeEventListener('keydown', s.onKey);
      s.drawer.removeEventListener('click', s.onClick);
      if (s.scrim) { s.scrim.removeEventListener('click', s.onScrim); s.scrim.hidden = true; }
      s.drawer.hidden = true;
      s.inert.forEach(function (x) { if (!x.was) x.el.removeAttribute('inert'); });
      this._open = null;
      if (s.trigger) { s.trigger.setAttribute('aria-expanded', 'false'); focusNoScroll(s.trigger); }
      var ev; try { ev = new CustomEvent('ecrm-drawer-close', { bubbles: true, detail: { reason: reason || 'close' } }); } catch (e) { ev = document.createEvent('CustomEvent'); ev.initCustomEvent('ecrm-drawer-close', true, false, { reason: reason || 'close' }); }
      s.drawer.dispatchEvent(ev);
    },
    isOpen: function () { return !!this._open; }
  };

  function initAll(root) {
    root = root || document;
    A.forEach.call(root.querySelectorAll('[role="radiogroup"]'), initRadioGroup);
    A.forEach.call(root.querySelectorAll('[role="listbox"]'), initListbox);
    A.forEach.call(root.querySelectorAll('[data-ecrm-press]'), initPressGroup);
    A.forEach.call(root.querySelectorAll('[data-ecrm-current]'), initCurrentGroup);
    A.forEach.call(root.querySelectorAll('table[data-ecrm-hierarchy]'), initHierarchy);
    A.forEach.call(root.querySelectorAll('table[data-ecrm-sortable]'), initSortable);
  }

  global.EcrmRecipes = { initAll: initAll, initRadioGroup: initRadioGroup, initListbox: initListbox, initPressGroup: initPressGroup, initCurrentGroup: initCurrentGroup, initHierarchy: initHierarchy, initSortable: initSortable, Drawer: Drawer };
})(window);
