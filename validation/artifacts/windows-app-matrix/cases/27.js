(() => {
  const clips = [
    { name: "Metro Rain", length: 58, color: "#38bdf8" },
    { name: "Amber Interlude", length: 46, color: "#c084fc" },
    { name: "Night Signal", length: 50, color: "#6ee7b7" }
  ];
  const requestedFades = [12, 38];
  const maximumFade = 16;
  const minimumSolo = 14;

  function makeTimeline(fades) {
    const tracks = clips.map((clip, index) => {
      const elapsed = clips.slice(0, index).reduce((total, item) => total + item.length, 0);
      const overlap = fades.slice(0, index).reduce((total, fade) => total + fade, 0);
      const start = elapsed - overlap;
      return { ...clip, start, end: start + clip.length };
    });
    const allStart = Math.max(...tracks.map(track => track.start));
    const allEnd = Math.min(...tracks.map(track => track.end));
    const collisionSeconds = Math.max(0, allEnd - allStart);
    const soloSeconds = clips[1].length - fades[0] - fades[1];
    const maxFade = Math.max(...fades);
    return { tracks, fades, runtime: tracks.at(-1).end, allStart, allEnd, collisionSeconds, soloSeconds, maxFade,
      safe: collisionSeconds === 0 && maxFade <= maximumFade && soloSeconds >= minimumSolo };
  }

  function adjustedFades() {
    const lead = Math.min(requestedFades[0], maximumFade, clips[1].length - minimumSolo);
    const finish = Math.min(requestedFades[1], maximumFade, clips[1].length - lead - minimumSolo);
    return [lead, finish];
  }

  function amplitude(index, trackIndex) {
    const envelope = .3 + .7 * Math.sin(Math.PI * (index + 3) / 80);
    const sample = Math.sin(index * 1.97 + trackIndex * .85) * Math.cos(index * .32 + trackIndex);
    return 3 + Math.abs(sample) * envelope * 19;
  }

  function render(step, result) {
    const current = result ?? makeTimeline([0, 0]);
    const x = seconds => 162 + 6.62 * seconds;
    const ticks = Array.from({ length: 9 }, (_, i) => {
      const seconds = i * 19;
      return `<path d="M ${x(seconds)} 29 V 249" stroke="#323752"/><text x="${x(seconds)}" y="21" fill="#9daac3" text-anchor="middle" font-size="13">${seconds}s</text>`;
    }).join("");
    const tracks = current.tracks.map((track, index) => {
      const y = 69 + 71 * index;
      const width = x(track.end) - x(track.start);
      const waveform = Array.from({ length: 75 }, (_, i) => {
        const cx = x(track.start) + 10 + i * (width - 20) / 75;
        const power = amplitude(i, index);
        return `M ${cx.toFixed(1)} ${(y-power).toFixed(1)} v ${(power*2).toFixed(1)}`;
      }).join(" ");
      return `<text x="6" y="${y+5}" fill="#e5e7ef" font-size="16" font-weight="650">${track.name}</text>
        <rect x="${x(track.start)}" y="${y-26}" rx="7" width="${width}" height="52" fill="${track.color}" fill-opacity=".18" stroke="${track.color}" stroke-opacity=".8"/>
        <path d="${waveform}" stroke="${track.color}" stroke-width="2" stroke-linecap="round"/>`;
    }).join("");
    const collision = step === 2 && current.collisionSeconds > 0 ?
      `<rect x="${x(current.allStart)}" y="32" width="${x(current.allEnd)-x(current.allStart)}" height="214" fill="#fb7185" fill-opacity=".45" stroke="#fda4af" stroke-dasharray="4 3"/>` : "";
    const headline = step === 3 ? "Ready for playout" : step === 2 ? "Three clips overlap" : "Mix timeline";
    return `<section class="fade-workspace"><div class="fade-toolbar"><h2>${headline}</h2>
      <span>03 TRACKS &nbsp; • &nbsp; ${current.runtime}s TIMELINE</span></div>
      <div class="fade-timeline"><svg viewBox="0 0 1190 262" role="img" aria-label="Three audio clips with their fade overlaps">
        ${ticks}${tracks}${collision}</svg></div>
      <div class="fade-stats"><article><small>MAXIMUM CROSSFADE</small><strong>${step < 2 ? "—" : current.maxFade + "s"}</strong><p>Limit of ${maximumFade}s per handoff</p></article>
        <article><small>THREE-TRACK COLLISION</small><strong class="${step === 2 ? "fade-danger" : ""}">${step < 2 ? "—" : current.collisionSeconds + "s"}</strong><p>No triple overlap permitted</p></article>
        <article><small>AMBER INTERLUDE SOLO</small><strong>${step < 2 ? "—" : Math.max(0,current.soloSeconds) + "s"}</strong><p>Minimum ${minimumSolo}s of clear audio</p></article></div></section>`;
  }

  window.caseDefinition = {
    id: "27", title: "Crossfade Timeline", kicker: "AUDIO PLAYOUT",
    scenario: "Validate a three-track handoff, then shorten the second crossfade to protect the middle track.",
    layout: "chart", accent: "#59c7ff", surface: "#111222", text: "#f0edff",
    actions: ["Load transition cues", "Run overlap check", "Rebuild safe fades"],
    expected: [
      { fades: [12, 38], runtime: 104 },
      { collisionSeconds: 4, safe: false, maxFade: 38, soloSeconds: -4 },
      { collisionSeconds: 0, safe: true, fades: [12, 16], runtime: 126, soloSeconds: 18 }
    ],
    run(step) {
      return makeTimeline(step === 3 ? adjustedFades() : requestedFades);
    },
    render,
    style: `
      .fade-workspace{background:#171a31;border:1px solid #323853;border-radius:19px;padding:22px 25px;height:461px;color:#eeeefe}
      .fade-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
      .fade-toolbar h2{font-size:27px;margin:0}.fade-toolbar span,.fade-stats small{font-size:12px;letter-spacing:.18em;color:#9fc6ef;font-weight:750}
      .fade-timeline{background:#101324;border-radius:12px;padding:12px 17px 0}.fade-timeline svg{display:block;width:100%;height:260px}
      .fade-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:16px}
      .fade-stats article{background:#232740;border:1px solid #343a59;border-radius:12px;padding:13px 16px}
      .fade-stats strong{display:block;font-size:30px;line-height:1.1;margin-top:5px}.fade-stats p{color:#b2bbd6;margin:4px 0 0;font-size:13px}
      .fade-danger{color:#fb7185}`
  };
})();
