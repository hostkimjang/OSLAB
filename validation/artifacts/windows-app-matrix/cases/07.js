(() => {
  const sampleRate = 12000;
  const seconds = 2;
  const fullScale = 32767;
  const waveSamples = Int16Array.from({ length: sampleRate * seconds }, (_, index) => {
    const tick = index / sampleRate;
    const envelope = Math.abs(Math.sin(tick * Math.PI * 2.5));
    const normal = Math.round(23000 * Math.sin(tick * Math.PI * 440) * envelope);
    if (index >= 3000 && index < 3120) return fullScale;
    return normal;
  });

  function inspect(samples) {
    let peak = 0;
    let clipped = 0;
    for (const sample of samples) {
      const absolute = Math.abs(sample);
      if (absolute >= fullScale) clipped++;
      peak = Math.max(peak, absolute);
    }
    return { sampleCount: samples.length, clipped, peak, durationMs: samples.length * 1000 / sampleRate };
  }

  function encodeWav(samples) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const tag = (offset, ascii) => Array.from(ascii).forEach((letter, index) => view.setUint8(offset + index, letter.charCodeAt(0)));
    tag(0, 'RIFF');
    view.setUint32(4, buffer.byteLength - 8, true);
    tag(8, 'WAVE');
    tag(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    tag(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    samples.forEach((sample, index) => view.setInt16(44 + index * 2, sample, true));
    return view;
  }

  function render(step, result) {
    const samples = step === 3 ? waveSamples.slice(6000, 18000) : waveSamples;
    const stride = Math.floor(samples.length / 100);
    const bars = Array.from({ length: 100 }, (_, bucket) => {
      const { peak, clipped } = inspect(samples.slice(bucket * stride, (bucket + 1) * stride));
      return '<i class="' + (step > 1 && clipped ? 'wave-clip' : '') + '" style="height:' + (4 + peak / fullScale * 155) + 'px"></i>';
    }).join('');
    const caption = step < 2 ? 'Preview waveform' : step === 2 ? result.clipped + ' clipped samples' : 'PCM WAV · ' + result.wavBytes.toLocaleString('en-US') + ' bytes';

    return '<div class="wave"><div class="wave-heading"><div><small>STUDIO / TRACK 01</small><h2>Morning station</h2></div><b>' + caption +
      '</b></div><div class="wave-bars">' + bars + '</div><div class="wave-ruler"><span>00:00.000</span><span>00:00.500</span>' +
      '<span>00:01.000</span>' + (step === 3 ? '' : '<span>00:01.500</span><span>00:02.000</span>') + '</div>' +
      '<div class="wave-footer"><span>12 kHz</span><span>Mono</span><span>16-bit PCM</span></div></div>';
  }

  window.caseDefinition = {
    id: '07',
    title: 'Wavecut',
    kicker: 'Audio export',
    scenario: 'Detect a clipped transient and trim a clean one-second segment to 16-bit PCM WAV.',
    layout: 'chart',
    accent: '#37dfda',
    surface: '#091c23',
    text: '#e8fcfa',
    actions: ['Load PCM track', 'Scan for clipping', 'Trim and encode WAV'],
    expected: [
      { sampleCount: 24000, rateHz: 12000, durationMs: 2000 },
      { clipped: 120, releaseAllowed: false },
      { clipped: 0, sampleCount: 12000, durationMs: 1000, wavBytes: 24044, format: 1, bitsPerSample: 16, dataBytes: 24000, releaseAllowed: true },
    ],
    style: '.wave{background:#091c23;color:#e8fcfa;padding:23px 27px;border-radius:12px}.wave-heading{display:flex;justify-content:space-between;align-items:center}.wave-heading small{color:#75d2d2;letter-spacing:.15em}.wave-heading h2{font-size:38px;margin:4px 0 16px}.wave-heading b{color:#78e6e2;background:#104849;border-radius:5px;padding:7px 13px}.wave-bars{height:175px;display:flex;align-items:center;gap:3px;background:repeating-linear-gradient(90deg,transparent 0 12.3%,#24565a 12.3% 12.5%),linear-gradient(transparent 0 49.5%,#497575 49.5% 50.5%,transparent 50.5%),#112a33;border:1px solid #225454;padding:0 12px;overflow:hidden}.wave-bars i{flex:1;background:#38d9d2;border-radius:2px;min-width:2px}.wave-bars i.wave-clip{background:#ff997d}.wave-ruler{display:flex;justify-content:space-between;color:#a8d6da;font:12px Consolas,monospace;margin:7px 0 20px}.wave-footer{display:flex;gap:9px}.wave-footer span{border:1px solid #3a686d;padding:5px 12px;font-size:12px;border-radius:4px}',
    run(step) {
      const samples = step === 3 ? waveSamples.slice(6000, 18000) : waveSamples;
      const details = inspect(samples);
      const result = { ...details, rateHz: sampleRate, releaseAllowed: details.clipped === 0 };
      if (step !== 3) return result;
      const wav = encodeWav(samples);
      return { ...result, wavBytes: wav.byteLength, format: wav.getUint16(20, true),
        bitsPerSample: wav.getUint16(34, true), dataBytes: wav.getUint32(40, true) };
    },
    render,
  };
})();
