(() => {
  const sample = [2029, 2044, 2035, 2068, 2027, 2019, 2048, 2032];
  const reference = { measured: 2035, certified: 2000 };
  const tolerance = { min: 1980, max: 2020 };
  const unit = (measurement) => (measurement / 100).toFixed(2);

  function inspect(readings) {
    const measurements = readings.map((value, i) => ({
      index: i + 1,
      value,
      accepted: value >= tolerance.min && value <= tolerance.max,
    }));
    const rejects = measurements.filter((row) => !row.accepted);
    return {
      measurements,
      passed: measurements.length - rejects.length,
      rejects: rejects.length,
      quarantine: rejects.map(({ index }) => index).join(','),
    };
  }

  function calibrate() {
    const offset = reference.measured - reference.certified;
    const inspection = inspect(sample.map((value) => value - offset));
    return {
      ...inspection,
      offsetMicrons: offset * 10,
      maxDeviationMicrons: Math.max(...inspection.measurements.map(({ value }) => Math.abs(value - reference.certified))) * 10,
    };
  }

  function plot(measurements, step) {
    const min = 1960;
    const max = 2080;
    const x = (index) => 64 + (index - 1) * 88;
    const y = (value) => 260 - (value - min) / (max - min) * 218;
    const background = [1960, 1980, 2000, 2020, 2040, 2060, 2080].map((value) => `<g>
      <text x="42" y="${y(value) + 4}" text-anchor="end" fill="#a4aadc" font-size="11">${unit(value)}</text>
      <path d="M50,${y(value)}H704" stroke="#3a395c" stroke-dasharray="4 4"/>
    </g>`).join('');
    const track = measurements.map(({ index, value }) => `${x(index)},${y(value)}`).join(' ');
    const markers = measurements.map(({ index, value, accepted }) => {
      const ink = step < 2 ? '#d6b0ff' : accepted ? '#81f0dc' : '#ffa39f';
      return `<g><circle cx="${x(index)}" cy="${y(value)}" r="6" stroke="#231f40" stroke-width="2" fill="${ink}"/>
        <text x="${x(index)}" y="${y(value) - 12}" text-anchor="middle" fill="${ink}" font-size="12" font-weight="bold">${unit(value)}</text>
        <text x="${x(index)}" y="282" text-anchor="middle" fill="#a4aadc" font-size="11">P${index}</text>
      </g>`;
    }).join('');
    return `<svg viewBox="0 0 715 296" role="img" aria-label="Thickness measurements by part with acceptance band">
      <rect x="50" y="${y(tolerance.max)}" width="654" height="${y(tolerance.min) - y(tolerance.max)}" fill="#244751"/>
      ${background}<polyline points="${track}" fill="none" stroke="#ba95f7" opacity=".8" stroke-width="2"/>${markers}
    </svg>`;
  }

  function render(step, result) {
    const measurements = result?.measurements ?? inspect(sample).measurements;
    const title = step === 3 ? 'Calibrated readings' : step === 2 ? 'Uncalibrated rejects' : 'Raw batch preview';
    const message = step === 3
      ? `Applied a −${result.offsetMicrons} µm correction. P${result.quarantine} still exceeds tolerance and is held.`
      : step === 2
        ? `${result.rejects} readings exceed tolerance. Check the gauge against the certified block.`
        : 'Reference block is certified at 20.00 mm. The gauge reads 20.35 mm on the same block.';
    return `<div class="gauge-panel">
      <section><div class="gauge-heading"><span>LOT Q-815 · GAUGE 02</span><span>THICKNESS / MM</span></div>${plot(measurements, step)}</section>
      <aside><span>INSPECTION RESULT</span><h2>${title}</h2><p>${message}</p>
        <div class="gauge-metric"><b>19.80–20.20</b><small>Acceptance band (mm)</small></div>
        <div class="gauge-metric"><b>${step >= 2 ? result.passed + ' / ' + sample.length : sample.length}</b><small>${step >= 2 ? 'Parts cleared' : 'Imported readings'}</small></div>
      </aside>
    </div>`;
  }

  window.caseDefinition = {
    id: '16',
    title: 'Gauge Lab',
    kicker: 'QUALITY CONTROL',
    scenario: 'Calibrate a biased digital gauge and isolate the one part still out of tolerance.',
    layout: 'chart',
    accent: '#d2b2ff',
    surface: '#151126',
    text: '#f5edff',
    actions: ['Load gauge readings', 'Apply tolerance rules', 'Calibrate and quarantine'],
    expected: [
      { readingCount: 8, nominal: '20.00', rawReference: '20.35' },
      { passed: 1, rejects: 7, quarantine: '1,2,3,4,5,7,8' },
      { passed: 7, rejects: 1, quarantine: '4', offsetMicrons: 350, maxDeviationMicrons: 330 },
    ],
    run(step) {
      if (step === 1) return { readingCount: sample.length, nominal: unit(reference.certified), rawReference: unit(reference.measured) };
      return step === 2 ? inspect(sample) : calibrate();
    },
    render,
    style: `
      .gauge-panel{display:grid;grid-template-columns:minmax(590px,2.3fr) minmax(245px,1fr);gap:20px;align-items:stretch}
      .gauge-panel section,.gauge-panel aside{background:#211c3a;border:1px solid #534874;border-radius:11px;color:#faefff}
      .gauge-panel section{padding:19px 16px 10px}.gauge-panel svg{height:304px;width:100%}
      .gauge-panel aside{padding:21px}.gauge-panel aside>span,.gauge-heading{color:#c6b0ef;font-size:12px;letter-spacing:.13em;font-weight:700}
      .gauge-heading{display:flex;justify-content:space-between;padding:0 4px 10px}.gauge-panel h2{font-size:27px;margin:5px 0 8px}
      .gauge-panel p{line-height:1.6;font-size:14px;color:#dbd1ef;margin:0 0 15px}
      .gauge-metric{padding:8px 13px;border-radius:7px;margin:5px 0 0;background:#31284a;border:1px solid #5f527d}
      .gauge-metric b,.gauge-metric small{display:block}.gauge-metric b{font-size:20px}.gauge-metric small{color:#d0c2eb}
    `,
  };
})();
