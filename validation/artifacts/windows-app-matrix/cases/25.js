(() => {
  const media = { width: 310, height: 210, margin: 12 };
  const artwork = [
    { name: "Outer contour", color: "#e879f9", points: [[8,26],[290,26],[306,42],[306,178],[290,194],[8,194],[8,26]] },
    { name: "Mark", color: "#5eead4", points: [[45,72],[78,111],[106,56],[137,143],[162,91],[197,113],[239,65]] },
    { name: "Baseline", color: "#facc15", points: [[42,167],[256,167]] }
  ];

  function bounds(paths) {
    const points = paths.flatMap(path => path.points);
    const xs = points.map(point => point[0]);
    const ys = points.map(point => point[1]);
    return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  }

  function fit(paths) {
    const region = bounds(paths);
    const scale = Math.min(
      (media.width - 2 * media.margin) / (region.maxX - region.minX),
      (media.height - 2 * media.margin) / (region.maxY - region.minY)
    );
    const centerX = (region.minX + region.maxX) / 2;
    const centerY = (region.minY + region.maxY) / 2;
    return paths.map(path => ({
      ...path,
      points: path.points.map(([x, y]) => [
        +((x - centerX) * scale + media.width / 2).toFixed(2),
        +((y - centerY) * scale + media.height / 2).toFixed(2)
      ])
    }));
  }

  function outside([x, y]) {
    return x < media.margin || x > media.width - media.margin ||
      y < media.margin || y > media.height - media.margin;
  }

  function render(step, result) {
    const paths = result?.paths ?? artwork;
    const waves = paths.map(path => `<polyline points="${path.points.map(point => point.join(",")).join(" ")}"
      stroke="${path.color}" fill="none" stroke-width="1.65" stroke-linejoin="round"/>`).join("");
    const faults = step === 2 ? paths.flatMap(path => path.points).filter(outside).map(([x, y]) =>
      `<circle cx="${x}" cy="${y}" r="3.7" fill="#fb7185" stroke="#1a142d" stroke-width="1.2"/>`).join("") : "";
    const label = step === 3 ? "WITHIN CUT WINDOW" : step === 2 ? "CLIPPED CONTOUR" : "PROOF PREVIEW";
    return `<div class="plot-workspace">
      <div class="plot-sheet"><svg viewBox="-22 -14 354 238" role="img" aria-label="Vector cut paths and safe material boundary">
        <defs><pattern id="plot-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 L 0 0 0 10" fill="none" stroke="#3b2d55" stroke-width=".5"/></pattern></defs>
        <rect width="310" height="210" rx="2" fill="#241935" stroke="#675584" stroke-width=".8"/>
        <rect width="310" height="210" fill="url(#plot-grid)"/>
        <rect x="12" y="12" width="286" height="186" rx="1" fill="none" stroke="#a98bcc" stroke-dasharray="3 2"/>
        ${waves}${faults}
        <text x="155" y="222" fill="#cab0e5" font-size="7" text-anchor="middle">310 mm • physical cut sheet</text>
      </svg></div>
      <aside class="plot-proof"><small>MATERIAL PROOF</small><h2>${label}</h2>
        <dl><div><dt>Toolpaths</dt><dd>${paths.length}</dd></div>
        <div><dt>Artwork width</dt><dd>${result?.artworkWidth ?? "—"} mm</dd></div>
        <div><dt>Outside safe area</dt><dd class="${step === 2 ? "plot-fault" : ""}">${step >= 2 ? result.outsideVertices : "—"}</dd></div></dl>
        <p>${step === 3 ? "Scale and center applied. Output coordinates stay inside the 12 mm margin." :
          step === 2 ? "Five control vertices cross the dashed safety boundary." :
          "Compare the artwork coordinates to the plotter's 12 mm margin."}</p>
      </aside></div>`;
  }

  window.caseDefinition = {
    id: "25", title: "Plotter Prep", kicker: "VECTOR PRODUCTION",
    scenario: "Reject a vinyl job outside the cut window, then fit the toolpaths without distorting the logo.",
    layout: "canvas", accent: "#e879f9", surface: "#191127", text: "#f5e8ff",
    actions: ["Load cut file", "Check cut boundaries", "Fit to material"],
    expected: [
      { toolpaths: 3, artworkWidth: 298, checked: false },
      { safe: false, outsideVertices: 5, artworkWidth: 298 },
      { safe: true, outsideVertices: 0, artworkWidth: 286, margin: 12 }
    ],
    run(step) {
      const paths = step === 3 ? fit(artwork) : artwork;
      const range = bounds(paths);
      const outsideVertices = paths.flatMap(path => path.points).filter(outside).length;
      return {
        paths, toolpaths: paths.length, artworkWidth: range.maxX - range.minX, margin: media.margin,
        checked: step >= 2, outsideVertices: step >= 2 ? outsideVertices : null,
        safe: step >= 2 ? outsideVertices === 0 : null
      };
    },
    render,
    style: `
      .plot-workspace{display:grid;grid-template-columns:minmax(0,1.87fr) minmax(0,1fr);gap:24px;align-items:stretch;height:460px}
      .plot-sheet,.plot-proof{border:1px solid #4e3b67;background:#211731;border-radius:16px;overflow:hidden}
      .plot-sheet{display:grid;place-items:center}.plot-sheet svg{display:block;width:100%;height:100%}
      .plot-proof{padding:39px 29px;color:#f5e8ff}.plot-proof small{color:#e879f9;letter-spacing:.26em;font-weight:700}
      .plot-proof h2{font-size:29px;line-height:1.1;margin:17px 0 28px}
      .plot-proof dl{margin:0}.plot-proof dl div{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #58416e;padding:12px 0;gap:12px}
      .plot-proof dt,.plot-proof p{color:#d0b8e7}.plot-proof dd{margin:0;font-size:24px;font-weight:750;font-variant-numeric:tabular-nums}
      .plot-proof p{margin-top:25px;line-height:1.55}.plot-fault{color:#fb7185}`
  };
})();
