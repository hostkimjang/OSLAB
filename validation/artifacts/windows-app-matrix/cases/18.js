(() => {
  const approved = [
    { name: "release.ini", kind: "Configuration", content: "release=2026.11\nchannel=stable\n", crc: "6D224E43" },
    { name: "regions.csv", kind: "Routing data", content: "region,manifest\nAPAC,12\nEMEA,20\n", crc: "622C06D8" },
    { name: "README.txt", kind: "Release notes", content: "Welcome to the offline release.\n", crc: "D4AAF7BE" }
  ];
  const candidate = approved.map((file) => file.name === "regions.csv"
    ? { ...file, content: "region,manifest\nAPAC,12\nEMEA,00\n" }
    : { ...file });

  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) {
      crc ^= byte;
      for (let index = 0; index < 8; index++) {
        crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
      }
    }
    return ((crc ^ -1) >>> 0).toString(16).padStart(8, "0").toUpperCase();
  }

  function compare(files) {
    return files.map(({ name, kind, crc, content }) => {
      const bytes = new TextEncoder().encode(content);
      const observed = crc32(bytes);
      return { name, kind, expected: crc, observed, bytes: bytes.length, matched: crc === observed };
    });
  }

  window.caseDefinition = {
    id: "18",
    title: "Package Ledger",
    kicker: "OFFLINE RELEASE INTEGRITY",
    scenario: "Compare staged release files with known CRC32 checksums before approval.",
    layout: "table",
    accent: "#b44312",
    surface: "#fff4cf",
    text: "#302014",
    actions: ["Load release package", "Verify file checksums", "Restore baseline copy"],
    expected: [
      { files: 3, pending: 3 },
      { matched: 2, mismatches: "regions.csv", observed: "61A8D2B6", approved: false },
      { matched: 3, mismatches: "", approved: true }
    ],
    run(step) {
      if (step === 1) return { files: candidate.length, pending: candidate.length };
      const rows = compare(step === 2 ? candidate : approved);
      const dirty = rows.filter((row) => !row.matched);
      return {
        rows, matched: rows.length - dirty.length, mismatches: dirty.map((row) => row.name).join(","),
        observed: dirty.map((row) => row.observed).join(","), approved: dirty.length === 0
      };
    },
    render(step, result) {
      const files = step < 2 ? candidate.map((file) => ({
        name: file.name, kind: file.kind, bytes: new TextEncoder().encode(file.content).length, expected: file.crc
      })) : result.rows;
      const rowColor = (file) => file.matched === false ? "#fde3dd" : "#fffcf1";
      return `<section style="padding:12px 18px;color:#302014">
        <div style="display:grid;grid-template-columns:1.25fr 2fr;gap:18px">
          <div style="background:#ffe17c;border-radius:18px;padding:27px;min-height:343px;">
            <div style="color:#8d390c;font-weight:800;font-size:15px">STABLE · BUILD 26.11</div>
            <h2 style="font-weight:850;font-size:46px;letter-spacing:-1.3px;line-height:1.08;margin:22px 0 13px">Release<br>manifest</h2>
            <p style="font-size:17px;line-height:1.45;margin:5px 0">Stored CRC32 fingerprints recorded from three approved package files.</p>
            <div style="font-size:31px;line-height:1.1;font-weight:850;margin-top:36px;color:${step === 2 ? "#822b1f" : "#513514"}">
              ${step < 2 ? "3 files staged" : step === 2 ? "Release blocked" : "Release approved"}
            </div>
            <p style="margin:12px 0 0;line-height:1.35">${step < 2 ? "Ready for comparison." : step === 2 ? "Routing data does not match its approved bytes." : "Restored routing data matches its recorded checksum."}</p>
          </div>
          <div style="background:#fffdf4;border:1px solid #e0cb96;border-radius:18px;padding:18px 20px">
            <div style="color:#9c501f;font-size:13px;font-weight:800">PACKAGE CONTENTS</div>
            <div style="font-size:24px;font-weight:750;margin:5px 0 14px">Expected and observed checksums</div>
            <div style="display:grid;grid-template-columns:1.4fr 1fr .9fr;gap:11px;padding:7px 12px;font-size:13px;color:#70572e;font-weight:800">
              <span>FILE</span><span>EXPECTED / OBSERVED</span><span>RESULT</span>
            </div>
            ${files.map((file) => `<div style="display:grid;grid-template-columns:1.4fr 1fr .9fr;align-items:center;gap:11px;border-radius:10px;padding:12px;background:${rowColor(file)};border:1px solid #ecdcba;margin-top:6px">
              <div><b style="display:block">${file.name}</b><small>${file.kind} · ${file.bytes} bytes</small></div>
              <span style="font-family:Consolas,monospace;font-weight:650">${file.expected}<br><span style="color:${file.matched === false ? "#a12715" : "#79623b"}">${file.observed ?? "Pending"}</span></span>
              <b style="color:${file.matched === false ? "#972812" : "#3c5b31"}">${file.matched === true ? "MATCH" : file.matched === false ? "MISMATCH" : "Queued"}</b>
            </div>`).join("")}
          </div>
        </div>
      </section>`;
    }
  };
})();
