(() => {
  const clip = {fps: 24, first: 101, last: 112};
  const sourceCels = Array.from({length: 12}, (_, index) => clip.first + index);
  const roughCut = [101, 102, 103, 104, 105, 106, 108, 108, 109, 110, 111, 112];
  const duration = cels => Math.round(cels.length * 1000 / clip.fps);

  function qualify(sequence) {
    const distinct = new Set(sequence);
    const missing = sourceCels.filter(cel => !distinct.has(cel));
    const repeated = [...new Set(sequence.filter((cel, index) => sequence.indexOf(cel) !== index))];
    const jumps = sequence.reduce((count, cel, index) => count + Number(index > 0 && cel !== sequence[index - 1] + 1), 0);
    return {sequence, missing, repeated, jumps, timelineFrames: sequence.length, durationMs: duration(sequence),
      conforms: missing.length === 0 && repeated.length === 0 && jumps === 0 && sequence.length === sourceCels.length};
  }

  function preview(cel) {
    const travel = (cel - clip.first) * 29;
    const lift = Math.round(Math.sin((cel - clip.first) / 11 * Math.PI) * -47);
    return `
      <svg viewBox="0 0 650 245" role="img" aria-label="Animation cel ${cel}">
        <defs>
          <linearGradient id="frame-sky" x2="0" y2="1"><stop stop-color="#130e36"/><stop offset="1" stop-color="#6d3b7a"/></linearGradient>
          <linearGradient id="frame-light"><stop stop-color="#c67bee"/><stop offset="1" stop-color="#fcacb9"/></linearGradient>
        </defs>
        <rect width="650" height="245" fill="url(#frame-sky)"/>
        <circle cx="486" cy="40" r="84" fill="#e48baf"/><circle cx="513" cy="29" r="36" fill="#f9aec5" opacity=".66"/>
        <path d="M0 185 94 105 167 149 233 120 301 183 419 134 650 202V245H0Z" fill="#48305a"/>
        <path d="M0 210 133 181 250 199 351 172 470 202 650 188V245H0Z" fill="#241b42"/>
        <path d="M0 220H650M0 236H650M70 245 227 217M189 245 292 217M310 245V216M456 245l-80-29M598 245l-148-29"
          fill="none" stroke="#9a5f9a" opacity=".48"/>
        <g transform="translate(${95 + travel} ${155 + lift})">
          <ellipse cx="50" cy="30" rx="70" ry="9" fill="#e896da" opacity=".28"/>
          <path d="M-37 22H4m-62 9H9" stroke="#eebdf4" stroke-width="3" opacity=".76"/>
          <path d="M1 11 31 7 49-8 92-8 113 9 139 15 142 24 14 25Z" fill="url(#frame-light)"/>
          <path d="M54-4h36l13 15H43Z" fill="#30244d"/>
          <rect x="114" y="18" width="18" height="3" rx="1.5" fill="#fcf0d0"/>
          <path d="M38 27H115" stroke="#ffcde7" stroke-width="3" stroke-linecap="round"/>
        </g>
      </svg>`;
  }

  function render(step, result) {
    const sequence = step >= 2 ? result.sequence : step === 1 ? roughCut : [];
    const selected = step >= 2 ? sequence[6] : clip.first;
    const skip = step >= 2 && !result.conforms;
    return `
      <div class="frame-console">
        <div class="frame-top">
          <div class="frame-screen">${preview(selected)}</div>
          <div class="frame-meta"><div class="frame-label">CUT 04 · THE LONG WAY HOME</div>
            <h2>Cel ${selected}</h2><p>${step === 0 ? "Import the studio cut sheet." :
              step === 1 ? "The imported cut is ready to conform." :
              skip ? "Frame 107 is skipped and frame 108 plays twice." : "Frame 107 is restored from the source reel."}</p>
            <div class="frame-spec"><span>Rate<strong>${clip.fps} fps</strong></span>
              <span>Duration<strong>${step ? duration(sequence) : "—"} ms</strong></span></div></div>
        </div>
        <div class="frame-track"><div class="frame-label">CEL TIMELINE · V1</div>
          <div class="frame-cels">${sourceCels.map((number, index) => {
            const actual = sequence[index];
            const bad = skip && (index === 6 || index === 7);
            return `<div class="${bad ? "frame-bad" : index === 6 && step === 3 ? "frame-good" : ""}">
              <span>${String(index + 1).padStart(2, "0")}</span><b>${actual ?? "—"}</b></div>`;
          }).join("")}</div>
          <div class="frame-label">${skip ? "HOLD · 2 continuity breaks" : step === 3 ? "MASTER · 12 unique cels" : "SOURCE · 101–112"}</div>
        </div>
      </div>`;
  }

  window.caseDefinition = {
    id: "22",
    title: "Framebridge",
    kicker: "ANIMATION CONFORM",
    scenario: "Find a skipped cel in an animation cut and rebuild a frame-accurate master.",
    layout: "canvas",
    accent: "#fba5d6",
    surface: "#19182a",
    text: "#fcf0ff",
    actions: ["Load rough cut", "Conform against source", "Restore original cel"],
    expected: [
      {fps: 24, sourceFrames: 12, timelineFrames: 12, durationMs: 500},
      {missing: [107], repeated: [108], jumps: 2, timelineFrames: 12, durationMs: 500, conforms: false},
      {missing: [], repeated: [], jumps: 0, timelineFrames: 12, durationMs: 500, conforms: true},
    ],
    run(step, previous) {
      if (step === 1) return {fps: clip.fps, sourceFrames: sourceCels.length, timelineFrames: roughCut.length,
        durationMs: duration(roughCut)};
      if (step === 2) return qualify(roughCut);
      const old = previous?.sequence ?? roughCut;
      const rebuilt = [...new Set(old.concat(sourceCels))].sort((a, b) => a - b);
      return qualify(rebuilt);
    },
    render,
    style: `
      .frame-console{padding:10px 0;color:#fcf0ff}.frame-top{display:grid;grid-template-columns:2.25fr 1fr;gap:20px}
      .frame-screen{overflow:hidden;height:240px;border:1px solid #644969;border-radius:10px;background:#291b40}.frame-screen svg{display:block;width:100%;height:100%;object-fit:cover}
      .frame-meta,.frame-track{background:#28243d;border-radius:10px;border:1px solid #4b405e;padding:20px;min-width:0}
      .frame-label{font:700 11px ui-monospace,monospace;letter-spacing:.1em;color:#e3aad4}
      .frame-meta h2{margin:18px 0 3px;font-size:39px;color:#ffd5f1}.frame-meta p{font-size:14px;color:#e8d5ef;margin:0 0 15px}
      .frame-spec{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#e3aad4}
      .frame-spec strong{display:block;color:#fcf0ff;font-size:21px;margin-top:2px}
      .frame-track{margin-top:15px;padding:15px 20px}.frame-cels{display:grid;grid-template-columns:repeat(12,1fr);gap:7px;margin:8px 0 12px}
      .frame-cels div{background:#4b355f;border:1px solid #6f547b;border-radius:5px;padding:7px 6px;font:700 15px ui-monospace,monospace;text-align:center}
      .frame-cels span{display:block;color:#efbae8;font-size:9px}.frame-cels div.frame-bad{background:#8b3355;border-color:#ff9eac}
      .frame-cels div.frame-good{background:#225b4c;border-color:#91d8b1}`,
  };
})();
