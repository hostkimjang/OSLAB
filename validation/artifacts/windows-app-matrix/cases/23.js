(() => {
  const job = {pages: 12, signaturePages: 8, trim: [148, 210], bleed: 3, stock: [420, 297]};
  const covers = ["FIELD NOTES", "INDEX", "TIDE", "MATERIAL", "FORM", "EXHIBIT", "SETTINGS", "SIGNAL",
    "SKETCH", "PROCESS", "CREDITS", "COLOPHON"];

  function impose() {
    const parts = Math.ceil(job.pages / job.signaturePages);
    const sheets = [];
    for (let signature = 0; signature < parts; signature++) {
      const globalPage = local => {
        const page = signature * job.signaturePages + local;
        return page <= job.pages ? page : null;
      };
      for (let sheet = 0; sheet < job.signaturePages / 4; sheet++) {
        const offset = sheet * 2;
        const low = 1 + offset;
        const high = job.signaturePages - offset;
        sheets.push({signature: signature + 1, sheet: sheet + 1,
          front: [globalPage(high), globalPage(low)], back: [globalPage(low + 1), globalPage(high - 1)]});
      }
    }
    return sheets;
  }

  function preflight(sheets) {
    const target = impose();
    const foldErrors = [];
    let blankSlots = 0;
    for (let i = 0; i < sheets.length; i++) {
      const sheet = sheets[i];
      for (const side of ["front", "back"]) {
        for (let position = 0; position < 2; position++) {
          if (sheet[side][position] === null) blankSlots++;
          if (sheet[side][position] !== target[i][side][position]) {
            foldErrors.push({position: `${sheet.signature}.${sheet.sheet} ${side} ${position === 0 ? "L" : "R"}`,
              expected: target[i][side][position], printed: sheet[side][position]});
          }
        }
      }
    }
    const requiredWidth = job.trim[0] * 2 + job.bleed * 2;
    const requiredHeight = job.trim[1] + job.bleed * 2;
    const stockFits = requiredWidth <= job.stock[0] && requiredHeight <= job.stock[1];
    return {sheets, signatureCount: new Set(sheets.map(sheet => sheet.signature)).size, sides: sheets.length * 2,
      blankSlots, foldErrors, stockFits, readyForPress: stockFits && foldErrors.length === 0};
  }

  function render(step, result) {
    const sheets = step >= 2 ? result.sheets : step === 1 ? impose() : [];
    const warnings = step >= 2 ? result.foldErrors : [];
    const previewSheet = step >= 2 ? sheets[0].back : sheets[0]?.front;
    const page = value => value == null ? "—" : String(value).padStart(2, "0");
    const pagePreview = (value, i) => `<div class="press-page p${i}"><span>ATELIER 014</span>
      <b>${value ? covers[value - 1] : "BLANK"}</b><div class="press-illustration"></div><strong>${page(value)}</strong></div>`;
    const preview = previewSheet ? previewSheet.map(pagePreview).join("") :
      '<div class="press-empty">Load a booklet to preview its folded signature.</div>';
    return `
      <div class="press-app">
        <div class="press-preview">
          <div class="press-label">JOB 014 · WINTER FIELD BOOKLET</div><h2>Press sheet preview</h2>
          <div class="press-stock">${preview}</div>
          <div class="press-info">A3 STOCK &nbsp; / &nbsp; A5 TRIM &nbsp; / &nbsp; 3 MM BLEED</div>
        </div>
        <div class="press-details">
          <div class="press-label">SADDLE STITCH · 8 PP</div><h2>Signature map</h2>
          <div class="press-map">
            <div class="press-cols"><span>Sheet</span><span>Front</span><span>Back</span></div>
            ${sheets.map((sheet, i) => `<div class="press-cols ${warnings.length && i < 2 ? "mismatch" : ""}">
              <span>${sheet.signature}.${sheet.sheet}</span><b>${sheet.front.map(page).join(" / ")}</b>
              <b>${sheet.back.map(page).join(" / ")}</b></div>`).join("")}
          </div>
          <div class="press-note ${warnings.length ? "warn" : ""}">${warnings.length ?
            "HOLD · pages 04 and 07 reverse at the fold" :
            step === 3 ? "PRESS READY · eight sides checked" : "12 source pages · 4 intentional blanks"}</div>
        </div>
      </div>`;
  }

  window.caseDefinition = {
    id: "23",
    title: "Signature Press",
    kicker: "PRINT PRODUCTION",
    scenario: "Catch transposed booklet pages in the folding proof before releasing an imposed press job.",
    layout: "table",
    accent: "#a44729",
    surface: "#f4eee0",
    text: "#312c23",
    actions: ["Load booklet specification", "Proof supplied imposition", "Rebuild and release plates"],
    expected: [
      {sourcePages: 12, pressSheets: 4, signatureCount: 2, blankSlots: 4, pressStock: "A3"},
      {signatureCount: 2, sides: 8, blankSlots: 4, stockFits: true, readyForPress: false,
        foldErrors: [{position: "1.1 back R", expected: 7, printed: 4}, {position: "1.2 back L", expected: 4, printed: 7}]},
      {signatureCount: 2, sides: 8, blankSlots: 4, stockFits: true, readyForPress: true, foldErrors: []},
    ],
    run(step) {
      const sheets = impose();
      if (step === 1) {
        const proof = preflight(sheets);
        return {sourcePages: job.pages, pressSheets: sheets.length, signatureCount: proof.signatureCount,
          blankSlots: proof.blankSlots, pressStock: "A3"};
      }
      if (step === 2) [sheets[0].back[1], sheets[1].back[0]] = [sheets[1].back[0], sheets[0].back[1]];
      return preflight(sheets);
    },
    render,
    style: `
      .press-app{display:grid;grid-template-columns:1.5fr 1fr;gap:22px;padding:10px 0;color:#312c23}
      .press-preview,.press-details{background:#fffaed;border:1px solid #d2bfa6;border-radius:8px;padding:21px;min-width:0}
      .press-label,.press-info{font:700 11px ui-monospace,monospace;color:#8b563e;letter-spacing:.1em}
      .press-app h2{font:700 29px Georgia,serif;margin:4px 0 14px}
      .press-stock{display:grid;grid-template-columns:repeat(2,1fr);gap:2px;min-height:220px;padding:12px;background:#b39374;border-radius:5px}
      .press-page{background:#f7dfb4;padding:12px;position:relative;overflow:hidden;min-width:0}.press-page.p1{background:#efd2a9}
      .press-page span{display:block;font:700 8px ui-monospace,monospace;letter-spacing:.18em}
      .press-page b{display:block;font:700 clamp(12px,2.1vw,26px) Georgia,serif;margin-top:5px;white-space:nowrap}
      .press-page strong{position:absolute;bottom:12px;right:12px;background:#542f22;color:#fff3db;border-radius:3px;padding:5px 8px}
      .press-illustration{height:126px;margin:8px 0;background:repeating-radial-gradient(ellipse at 100% 90%,#a14530 0 6px,#eab88b 7px 11px,#562e26 12px 17px);transform:skewY(-5deg)}
      .press-page.p1 .press-illustration{background:repeating-linear-gradient(142deg,#202b24 0 10px,#918d5f 10px 22px,#c1814e 22px 25px)}
      .press-info{margin-top:13px}.press-empty{grid-column:span 2;display:grid;place-items:center;color:#fff8e2;text-align:center;padding:12px}
      .press-map{border-top:1px solid #ba9b7c}.press-cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;border-bottom:1px solid #e1cdb3;padding:9px 6px;font:13px ui-monospace,monospace}
      .press-cols.mismatch{background:#f5d5c1;color:#8c392b}.press-note{margin-top:19px;background:#e6edce;color:#365229;padding:10px;border-radius:4px;font-weight:700;font-size:13px}
      .press-note.warn{background:#f5d5c1;color:#8c392b}`,
  };
})();
