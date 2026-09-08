(() => {
  const { glyphSvg, ringSvg, sideNotchPath, pillPath, px } = window.CodenotchDesign;

  const api = () => window.__TAURI__;
  const invoke = (cmd, args) => {
    if (!api()?.core?.invoke) return Promise.reject(new Error("Tauri API unavailable"));
    return api().core.invoke(cmd, args);
  };
  const listen = (event, handler) => {
    if (!api()?.event?.listen) return Promise.resolve(() => {});
    return api().event.listen(event, handler);
  };

  const appEl = document.getElementById("app");
  const cellsEl = document.getElementById("cells");
  const tooltipEl = document.getElementById("tooltip");
  const notchPath = document.getElementById("notch-path");
  const notchShape = document.getElementById("notch-shape");
  const notchWrap = document.getElementById("notch-wrap");
  const orb = document.getElementById("orb");
  const edgeHotzone = document.getElementById("edge-hotzone");

  let snapshots = [];
  let prefs = {
    notchVisibility: "onHover",
    notchEdge: "right",
    disconnectedProviders: [],
    launchAtLogin: false,
  };
  let expanded = false;
  let pinned = false;
  let hoverCell = null;
  let foldTimer = null;
  let tooltipTimer = null;
  let lastOverlaySize = "";

  function applyPrefs() {
    appEl.dataset.edge = prefs.notchEdge || "right";
    appEl.dataset.visibility = prefs.notchVisibility || "onHover";
    if (prefs.notchVisibility === "alwaysShow") setExpanded(true);
    else if (prefs.notchVisibility === "hidden") setExpanded(false);
    updateShape();
  }

  function setExpanded(value) {
    expanded = value;
    appEl.dataset.expanded = value ? "true" : "false";
    updateShape();
    if (!value) hideTooltip(true);
    reportHitRegions();
  }

  function mirrorPath(d, depth) {
    return d
      .replace(/([ML])\s*([-\d.]+)\s+([-\d.]+)/g, (_, cmd, x, y) => `${cmd} ${depth - Number(x)} ${y}`)
      .replace(
        /A\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d)\s+(\d)\s+([-\d.]+)\s+([-\d.]+)/g,
        (_, r1, r2, rot, large, sweep, x, y) =>
          `A ${r1} ${r2} ${rot} ${large} ${sweep === "1" ? "0" : "1"} ${depth - Number(x)} ${y}`
      );
  }

  function contentLength(cellCount) {
    // Cap-height → font size, same as Typography.swift / CSS --font-percent.
    const labelH = px(27) / 0.714;
    return (
      px(69.5) +
      cellCount * (px(117) + px(26.9) + labelH) +
      Math.max(0, cellCount - 1) * px(83.5) +
      px(50.1)
    );
  }

  function expandedLength() {
    const count = Math.max(snapshots.length, 1);
    const vertical = prefs.notchEdge === "right" || prefs.notchEdge === "left";
    const body = vertical
      ? Math.max(contentLength(count), cellsEl.scrollHeight - 2 * px(103))
      : Math.max(count * px(117) + Math.max(0, count - 1) * px(83.5) + 2 * px(50.1),
        cellsEl.scrollWidth - 2 * px(103));
    return body + 2 * px(103);
  }

  function updateShape() {
    const vertical = prefs.notchEdge === "right" || prefs.notchEdge === "left";
    const depth = expanded ? px(186) : px(26);
    const length = expanded ? expandedLength() : px(210);

    const w = vertical ? depth : length;
    const h = vertical ? length : depth;
    notchShape.setAttribute("viewBox", `0 0 ${w} ${h}`);
    notchWrap.style.width = `${vertical ? depth : length}px`;
    notchWrap.style.minHeight = `${vertical ? length : depth}px`;
    notchWrap.style.height = `${vertical ? length : depth}px`;

    let d = expanded ? sideNotchPath(depth, length) : pillPath(depth, length);
    if (prefs.notchEdge === "left") d = mirrorPath(d, depth);
    notchPath.setAttribute("d", d);
    if (prefs.notchEdge === "top") {
      notchPath.setAttribute("transform", `matrix(0 1 -1 0 ${length} 0)`);
      notchPath.setAttribute("d", mirrorPath(d, depth));
    } else if (prefs.notchEdge === "bottom") {
      notchPath.setAttribute("transform", "matrix(0 1 1 0 0 0)");
    } else {
      notchPath.removeAttribute("transform");
    }
  }

  function renderCells() {
    cellsEl.innerHTML = "";
    snapshots.forEach((snap, index) => {
      const cell = document.createElement("div");
      cell.className = `cell${snap.stale ? " stale" : ""}`;
      cell.style.animationDelay = `${index * 45}ms`;
      cell.dataset.id = snap.id;

      const ring = document.createElement("div");
      ring.className = "ring";
      const frac = snap.hasReading ? snap.usedFraction ?? 0 : 0;
      const color = snap.hasReading ? snap.bandColor : "#303030";
      ring.innerHTML = ringSvg(snap.hasReading ? frac : 0, color);
      const glyph = document.createElement("div");
      glyph.className = "glyph";
      glyph.innerHTML = glyphSvg(snap.glyph);
      ring.appendChild(glyph);

      const percent = document.createElement("div");
      percent.className = "percent";
      percent.textContent = snap.hasReading ? snap.headlineText : "—";

      cell.appendChild(ring);
      cell.appendChild(percent);

      cell.addEventListener("pointerenter", () => {
        hoverCell = snap.id;
        clearTimeout(tooltipTimer);
        showTooltip(snap);
      });
      cell.addEventListener("pointerleave", () => {
        tooltipTimer = setTimeout(() => {
          if (hoverCell === snap.id) hideTooltip(false);
        }, 250);
      });
      cell.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await invoke("refresh_provider", { id: snap.id });
          snapshots = await invoke("refresh_all");
          renderCells();
        } catch (err) {
          console.error(err);
        }
      });

      cellsEl.appendChild(cell);
    });
    updateShape();
    requestAnimationFrame(() => {
      updateShape();
      requestAnimationFrame(() => {
        updateShape();
        reportHitRegions();
      });
    });
  }

  function reportHitRegions() {
    reportOverlaySize();
    const rects = [];
    const add = (el, pad = 0) => {
      if (!el || el.hidden) return;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      const x = Math.max(0, r.left - pad);
      const y = Math.max(0, r.top - pad);
      const right = Math.min(innerWidth, r.right + pad);
      const bottom = Math.min(innerHeight, r.bottom + pad);
      if (right > x && bottom > y) rects.push({ x, y, w: right - x, h: bottom - y });
    };

    if (prefs.notchVisibility !== "hidden") {
      add(notchWrap, 8);
      if (expanded) add(orb, 12);
      add(edgeHotzone, 0);
      if (!tooltipEl.hidden) add(tooltipEl, 4);
    }

    invoke("set_input_regions", { rects }).catch(() => {});
  }

  function reportOverlaySize() {
    // Reserve the expanded content and tooltip, even while folded. Measuring
    // #stage (the viewport) here creates a resize -> larger viewport feedback loop.
    const vertical = prefs.notchEdge === "right" || prefs.notchEdge === "left";
    const length = expandedLength();
    const padding = 48; // Space for the orb and shadows, away from the bezel.
    const cardWidth = px(600) + 16;
    const cardHeight = tooltipEl.hidden ? 240 : Math.max(240, tooltipEl.offsetHeight);
    const depth = px(186);
    const gap = px(28);
    const width = Math.ceil(vertical
      ? depth + gap + cardWidth + padding
      : Math.max(length, cardWidth) + 2 * padding);
    const height = Math.ceil(vertical
      ? Math.max(length, cardHeight) + 2 * padding
      : depth + gap + cardHeight + padding);
    const key = `${width}x${height}`;
    if (key === lastOverlaySize) return;
    lastOverlaySize = key;
    invoke("set_overlay_size", { width, height }).catch(() => { lastOverlaySize = ""; });
  }

  function showTooltip(snap) {
    const title = tooltipEl.querySelector(".tooltip-title");
    const glyph = tooltipEl.querySelector(".tooltip-glyph");
    const windows = tooltipEl.querySelector(".tooltip-windows");
    title.textContent = `${snap.displayName} Usage`;
    glyph.innerHTML = glyphSvg(snap.glyph);
    windows.innerHTML = "";

    if (!snap.windows?.length) {
      const empty = document.createElement("div");
      empty.className = "tooltip-summary";
      empty.style.color = "var(--text-secondary)";
      if (snap.status?.kind === "needsAuth") {
        empty.textContent = "Sign in with the provider’s own app.";
      } else if (snap.status?.kind === "error") {
        empty.textContent = snap.status.message || "Error";
      } else {
        empty.textContent = "Waiting for the first reading…";
      }
      windows.appendChild(empty);
    } else {
      for (const w of snap.windows) {
        const block = document.createElement("div");
        block.className = "tooltip-window";
        block.innerHTML = `
          <div class="tooltip-window-row">
            <span>${w.label}</span>
            <span>${w.resetCopy || ""}</span>
          </div>
          <div class="bar"><span style="width:${Math.min(100, (w.usedFraction ?? 0) * 100)}%;background:${w.bandColor || "#00FF88"}"></span></div>
          <div class="tooltip-summary">${w.summary}</div>`;
        windows.appendChild(block);
      }
    }
    tooltipEl.hidden = false;
    reportHitRegions();
  }

  function hideTooltip(immediate) {
    const run = () => {
      tooltipEl.hidden = true;
      hoverCell = null;
      reportHitRegions();
    };
    if (immediate) run();
    else tooltipTimer = setTimeout(run, 0);
  }

  function onStageEnter() {
    clearTimeout(foldTimer);
    if (prefs.notchVisibility === "hidden") return;
    setExpanded(true);
  }

  function onStageLeave() {
    if (prefs.notchVisibility === "alwaysShow" || pinned) return;
    foldTimer = setTimeout(() => setExpanded(false), 450);
  }

  notchWrap.addEventListener("pointerenter", onStageEnter);
  notchWrap.addEventListener("pointerleave", onStageLeave);
  edgeHotzone.addEventListener("pointerenter", onStageEnter);
  tooltipEl.addEventListener("pointerenter", () => clearTimeout(foldTimer));
  tooltipEl.addEventListener("pointerleave", onStageLeave);
  notchWrap.addEventListener("transitionend", reportHitRegions);
  new ResizeObserver(reportHitRegions).observe(notchWrap);

  orb.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await invoke("open_settings");
    } catch (err) {
      console.error(err);
    }
  });

  notchWrap.addEventListener("click", () => {
    if (prefs.notchVisibility === "alwaysShow") return;
    pinned = !pinned;
    if (pinned) setExpanded(true);
  });

  function demoSnapshots() {
    return [
      {
        id: "claude",
        displayName: "Claude",
        glyph: "claude",
        headlineText: "73%",
        usedFraction: 0.73,
        bandColor: "#FF3F00",
        hasReading: true,
        windows: [
          {
            label: "Current session",
            resetCopy: "Resets in 51 min",
            usedFraction: 0.73,
            summary: "73% Used · 27% left",
            bandColor: "#FF3F00",
          },
          {
            label: "All models",
            resetCopy: "Resets Thu 12:00 AM",
            usedFraction: 0.07,
            summary: "7% Used · 93% left",
            bandColor: "#00FF88",
          },
        ],
      },
      {
        id: "codex",
        displayName: "Codex",
        glyph: "openai",
        headlineText: "21%",
        usedFraction: 0.21,
        bandColor: "#00FF88",
        hasReading: true,
        windows: [
          {
            label: "Current session",
            resetCopy: "Resets in 3 h",
            usedFraction: 0.21,
            summary: "21% Used · 79% left",
            bandColor: "#00FF88",
          },
        ],
      },
      {
        id: "cursor",
        displayName: "Cursor",
        glyph: "cursor",
        headlineText: "52%",
        usedFraction: 0.52,
        bandColor: "#F2FF00",
        hasReading: true,
        windows: [
          {
            label: "Included usage",
            resetCopy: "Resets Thu 12:00 AM",
            usedFraction: 0.52,
            summary: "52% Used · 48% left",
            bandColor: "#F2FF00",
          },
        ],
      },
    ];
  }

  async function boot() {
    try {
      prefs = await invoke("get_preferences");
      applyPrefs();
      snapshots = await invoke("get_snapshots");
      if (!snapshots.length) snapshots = await invoke("refresh_all");
      renderCells();
      // Demo / first paint: show the expanded notch so layout bugs are visible immediately.
      if (snapshots.length && prefs.notchVisibility !== "hidden") setExpanded(true);
      reportHitRegions();
      window.addEventListener("resize", () => {
        updateShape();
        reportHitRegions();
      });
    } catch (err) {
      console.error("boot failed", err);
      snapshots = demoSnapshots();
      setExpanded(true);
      renderCells();
    }

    await listen("snapshots-updated", (event) => {
      snapshots = event.payload;
      renderCells();
    });
    await listen("preferences-changed", (event) => {
      prefs = event.payload;
      applyPrefs();
      renderCells();
    });
  }

  boot();
})();
