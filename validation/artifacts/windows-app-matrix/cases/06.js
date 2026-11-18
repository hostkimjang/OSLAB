(() => {
  const paper = '#ffffff';
  const palette = [
    { name: 'Primary text', color: '#000000', sample: 'Account summary' },
    { name: 'Secondary text', color: '#777777', sample: 'Last payment Apr 18' },
    { name: 'Critical text', color: '#ff0000', sample: 'Card verification failed' },
  ];
  const revised = ['#000000', '#595959', '#990000'];
  const targetRatio = 4.5;

  function luminance(hex) {
    let index = 0;
    return [0.2126, 0.7152, 0.0722].reduce((total, weight) => {
      const channel = parseInt(hex.slice(1 + index, 3 + index), 16) / 255;
      index += 2;
      const linear = channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
      return total + weight * linear;
    }, 0);
  }

  function audit(tokens) {
    return tokens.map(({ name, color }) => {
      const ratio = (luminance(paper) + 0.05) / (luminance(color) + 0.05);
      return { name, color, ratio: Number(ratio.toFixed(2)), passes: ratio >= targetRatio };
    });
  }

  function render(step, result) {
    const tokens = step === 3 ? palette.map((token, index) => ({ ...token, color: revised[index] })) : palette;
    const checks = step > 1 ? result.tokens : [];
    const status = step < 2 ? 'Awaiting audit' : result.releaseAllowed ? 'All color pairs pass' : 'Two color pairs below 4.5:1';
    const samples = tokens.map((token, index) => {
      const check = checks[index];
      return '<div class="contrast-pair"><i style="background:' + token.color + '"></i><div><b>' + token.name +
        '</b><small>' + token.color.toUpperCase() + ' on white</small></div>' +
        (check ? '<strong class="' + (check.passes ? 'contrast-good' : 'contrast-bad') + '">' + check.ratio.toFixed(2) + ':1</strong>' : '') +
        '</div>';
    }).join('');
    const preview = tokens.map((token) => '<p style="color:' + token.color + '">' + token.sample + '</p>').join('');

    return '<div class="contrast"><div><small>APPEARANCE TOKENS</small><h2>Readability check</h2><p>Minimum contrast for this release is 4.5:1.</p>' +
      '<div class="contrast-tests">' + samples + '</div><div class="contrast-note">' + status + '</div></div>' +
      '<div class="contrast-preview"><small>LIVE BILLING PREVIEW</small><div class="contrast-card">' + preview + '</div></div></div>';
  }

  window.caseDefinition = {
    id: '06',
    title: 'Contrast Studio',
    kicker: 'Accessibility review',
    scenario: 'Detect unreadable text colors and verify revised theme tokens against a 4.5:1 target.',
    layout: 'board',
    accent: '#aebdff',
    surface: '#221b3a',
    text: '#f4f2ff',
    actions: ['Load billing theme', 'Measure text contrast', 'Apply and audit repair'],
    expected: [
      { tokenCount: 3, background: '#ffffff' },
      { failed: ['Secondary text', 'Critical text'], worstContrast: 4, releaseAllowed: false },
      { failed: [], worstContrast: 7, releaseAllowed: true },
    ],
    style: '.contrast{display:grid;grid-template-columns:1.25fr 1fr;gap:35px;background:linear-gradient(135deg,#221b3a,#30224d);color:#f4f2ff;padding:27px;border-radius:15px}.contrast h2{font-size:34px;margin:4px 0}.contrast p{margin:6px 0 24px;color:#d6c8eb}.contrast small{display:block;color:#c1b1e3;letter-spacing:.08em;font-size:11px}.contrast-tests{display:grid;gap:8px}.contrast-pair{display:grid;grid-template-columns:32px 1fr auto;gap:12px;background:#43325d;border:1px solid #675681;align-items:center;padding:9px 12px;border-radius:8px}.contrast-pair i{width:26px;height:26px;border:1px solid #c9badf;border-radius:5px}.contrast-pair small{margin-top:2px}.contrast-good{color:#b3edba}.contrast-bad{color:#ffbbaa}.contrast-note{margin-top:14px;color:#ddcbf8;font-weight:650}.contrast-preview{align-self:center}.contrast-card{margin-top:10px;background:#fff;padding:30px;border-radius:18px}.contrast-card p{margin:12px 0;font-size:18px}.contrast-card p:first-child{font-size:28px;font-weight:750}',
    run(step) {
      if (step === 1) return { tokenCount: palette.length, background: paper };
      const active = step === 3 ? palette.map((token, index) => ({ ...token, color: revised[index] })) : palette;
      const tokens = audit(active);
      const failed = tokens.filter((token) => !token.passes).map((token) => token.name);
      return {
        tokens,
        failed,
        worstContrast: Math.floor(Math.min(...tokens.map((token) => token.ratio))),
        releaseAllowed: failed.length === 0,
      };
    },
    render,
  };
})();
