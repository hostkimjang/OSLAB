(() => {
  const tile = { width: 80, height: 50 };
  const palettes = [
    [[222, 172, 139], [255, 218, 165], [180, 88, 52], [92, 52, 43]],
    [[102, 162, 175], [206, 231, 216], [55, 119, 109], [16, 57, 60]],
    [[211, 166, 139], [243, 221, 187], [155, 79, 51], [73, 39, 60]],
    [[88, 107, 149], [207, 182, 192], [81, 110, 149], [31, 38, 71]],
    [[125, 156, 139], [225, 238, 184], [119, 115, 64], [46, 62, 38]],
  ];
  const catalog = [
    { id: 'D01', label: 'Copper Dunes', scene: 0 },
    { id: 'D02', label: 'Pine Lake', scene: 1 },
    { id: 'D03', label: 'Atrium Drift', scene: 2, rotate: true },
    { id: 'D04', label: 'Harbor Mist', scene: 3 },
    { id: 'D05', label: 'Valley Run', scene: 4 },
    { id: 'D06', label: 'Harbor Mist – copy', scene: 3 },
  ];

  function mix(a, b, weight, grain) {
    return a.map((value, i) => Math.max(0, Math.min(255, Math.round(value + (b[i] - value) * weight + grain))));
  }

  function photograph(scene) {
    const { width, height } = tile;
    const pixels = new Uint8Array(width * height * 3);
    const [sky, horizon, rock, shadow] = palettes[scene];
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const grain = ((x * 37 + y * 119 + scene * 41) % 17) - 8;
        const ridge = 28 - 8 * Math.sin((x + scene * 10) / 17) -
          9 * Math.exp(-Math.pow((x - 32 - 5 * scene) / 13, 2));
        const foreground = 38 + 5 * Math.cos((x + scene * 9) / 15) - 3 * Math.sin(x / 8);
        const sun = Math.hypot(x - 58 + scene * 5, y - 13);
        let color;
        if (scene === 2 && (x < 18 || x > 64 || (y < 20 && Math.hypot(x - 41, y - 26) > 22))) {
          color = mix(rock, shadow, (y + x % 5) / (height + 6), grain);
        } else if (y > foreground) {
          color = mix(rock, shadow, .62 + .28 * Math.sin(y / 4 + x / 20), grain);
        } else if (y > ridge) {
          color = mix(rock, shadow, .25 + .24 * Math.cos(x / 10 + y / 3), grain);
        } else if (sun < 6 - scene / 4) {
          color = mix(horizon, [252, 246, 221], .78, grain);
        } else {
          color = mix(sky, horizon, y / 33, grain);
        }
        pixels.set(color, (y * width + x) * 3);
      }
    }
    return { width, height, pixels };
  }

  function rotateClockwise(image) {
    const width = image.height;
    const height = image.width;
    const pixels = new Uint8Array(width * height * 3);
    for (let y = 0; y < image.height; y += 1) {
      for (let x = 0; x < image.width; x += 1) {
        const source = (y * image.width + x) * 3;
        pixels.set(image.pixels.subarray(source, source + 3), (x * width + width - y - 1) * 3);
      }
    }
    return { width, height, pixels };
  }

  function equal(a, b) {
    return a.image.width === b.image.width && a.image.height === b.image.height &&
      a.image.pixels.every((byte, i) => byte === b.image.pixels[i]);
  }

  function jobs() {
    return catalog.map(entry => {
      const image = photograph(entry.scene);
      return { ...entry, image: entry.rotate ? rotateClockwise(image) : image };
    });
  }

  function inspect(entries) {
    const unique = [];
    const duplicates = [];
    const portraitIds = [];
    for (const entry of entries) {
      const first = unique.find(other => equal(entry, other));
      if (first) duplicates.push(entry.id + '→' + first.id);
      else unique.push(entry);
      if (entry.image.height > entry.image.width) portraitIds.push(entry.id);
    }
    return { unique, duplicates, portraitIds };
  }

  function orient(entry) {
    let image = entry.image;
    if (entry.rotate) {
      for (let turn = 0; turn < 3; turn += 1) image = rotateClockwise(image);
    }
    return image;
  }

  function bitmap({ width, height, pixels }) {
    const stride = Math.ceil(width * 3 / 4) * 4;
    const bytes = new Uint8Array(54 + height * stride);
    const header = new DataView(bytes.buffer);
    header.setUint16(0, 0x4d42, true);
    header.setUint32(2, bytes.length, true);
    header.setUint32(10, 54, true);
    header.setUint32(14, 40, true);
    header.setInt32(18, width, true);
    header.setInt32(22, -height, true);
    header.setUint16(26, 1, true);
    header.setUint16(28, 24, true);
    header.setUint32(34, height * stride, true);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const source = (y * width + x) * 3;
        const target = 54 + y * stride + x * 3;
        bytes[target] = pixels[source + 2];
        bytes[target + 1] = pixels[source + 1];
        bytes[target + 2] = pixels[source];
      }
    }
    return bytes;
  }

  function contactSheet(entries) {
    const gutter = 7;
    const columns = 3;
    const rows = Math.ceil(entries.length / columns);
    const width = columns * tile.width + (columns + 1) * gutter;
    const height = rows * tile.height + (rows + 1) * gutter;
    const pixels = new Uint8Array(width * height * 3).fill(249);
    entries.forEach((entry, index) => {
      const image = orient(entry);
      const x = gutter + (index % columns) * (tile.width + gutter);
      const y = gutter + Math.floor(index / columns) * (tile.height + gutter);
      for (let row = 0; row < image.height; row += 1) {
        const start = row * image.width * 3;
        pixels.set(image.pixels.subarray(start, start + image.width * 3), ((y + row) * width + x) * 3);
      }
    });
    return bitmap({ pixels, width, height });
  }

  function source(bytes) {
    let payload = '';
    for (let end = 0; end < bytes.length; end += 8192) {
      payload += String.fromCharCode(...bytes.subarray(end, end + 8192));
    }
    return 'data:image/bmp;base64,' + btoa(payload);
  }

  function render(step, result) {
    const entries = jobs();
    const review = inspect(entries);
    const sheet = step === 3
      ? '<figure class="proof-composite"><img src="' + source(contactSheet(review.unique)) +
        '" alt="Final contact sheet with five approved photographs"><figcaption>contact-sheet.bmp / ' +
        result.dimensions.join(' × ') + ' px / ' + result.tiles + ' photographs</figcaption></figure>'
      : '<div class="proof-grid">' + entries.map(entry => {
        const highlight = step === 2 && (entry.id === 'D03' || entry.id === 'D06');
        const image = step === 0 ? '<div class="proof-placeholder"></div>'
          : '<img src="' + source(bitmap(entry.image)) + '" alt="' + entry.label + '">';
        const status = !highlight ? entry.id : entry.id === 'D03' ? 'Rotate' : 'Duplicate';
        return '<figure class="' + (highlight ? 'proof-flag' : '') + '">' + image +
          '<figcaption>' + entry.label + '<b>' + status + '</b></figcaption></figure>';
      }).join('') + '</div>';
    return '<style> .proof{height:100%;display:grid;grid-template-columns:1fr 250px;gap:22px;padding:6px;color:#442334;font-family:"Segoe UI",sans-serif} .proof figure,.proof aside{margin:0} .proof-grid{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2, max-content);gap:13px} .proof-grid figure,.proof-composite,.proof aside{background:#fff8f5;border:1px solid #e4bdb7;border-radius:10px;padding:8px} .proof-grid figure.proof-flag{border-color:#bd3555;box-shadow:inset 0 0 0 1px #bd3555} .proof-grid img,.proof-placeholder{display:block;width:100%;height:147px;object-fit:contain;background:#321c28;border-radius:5px} .proof-placeholder{background:linear-gradient(152deg,#edccc1 49.8%,#f8ded7 50%)} .proof figcaption{display:flex;justify-content:space-between;align-items:center;gap:7px;font-size:13px;padding:7px 3px 2px;white-space:nowrap} .proof figcaption b{font-size:11px;letter-spacing:.06em;font-weight:700;color:#9b415a} .proof-composite{align-self:start;padding:12px!important} .proof-composite img{display:block;margin:auto;width:100%;height:372px;object-fit:contain} .proof aside{padding:17px 15px;align-self:start} .proof h2{font-size:19px;letter-spacing:-.03em;margin:0 0 18px} .proof aside strong,.proof aside span{display:block} .proof aside strong{font-size:33px;font-weight:730;line-height:1.05;color:#b4234d} .proof aside span{font-size:12px;color:#704855;margin:2px 0 18px} .proof aside p{font-size:14px;line-height:1.45;margin:3px 0 1px} </style><div class="proof">' + sheet + '<aside><h2>Studio proof</h2><strong>' +
      (step === 0 ? '6' : step === 1 ? result.files : step === 2 ? result.distinctPhotos : result.tiles) +
      '</strong><span>' + (step >= 2 ? 'Distinct photographs' : 'Source assets') + '</span><strong>' +
      (step < 2 ? '—' : step === 2 ? result.duplicatePairs.length + result.orientationWarnings.length : '0') +
      '</strong><span>Unresolved issues</span><p>' + [
        'Load the six source photographs from the studio intake batch.',
        'Photo bytes loaded. Check the proof before assembling the sheet.',
        'D03 needs rotation. D06 matches D04 pixel for pixel.',
        'Duplicate removed, orientation corrected, and the bitmap contact sheet assembled.',
      ][step] + '</p></aside></div>';
  }

  window.caseDefinition = {
    id: '03', title: 'Photo Proof Studio', kicker: 'Photography production',
    scenario: 'Reject a duplicate photo, correct a rotated exposure, and assemble a bitmap contact sheet.',
    layout: 'board', accent: '#b4234d', surface: '#f9e8e3', text: '#442334',
    actions: ['Load six captures', 'Inspect the proof', 'Assemble corrected sheet'],
    expected: [
      { files: 6, pixelCount: 24000 },
      { distinctPhotos: 5, duplicatePairs: ['D06→D04'], orientationWarnings: ['D03'] },
      { tiles: 5, dimensions: [268, 121], bitmapBytes: 97338, assetOrder: ['D01', 'D02', 'D03', 'D04', 'D05'] },
    ],
    run(step) {
      const entries = jobs();
      if (step === 1) return { files: entries.length, pixelCount: entries.reduce((total, entry) => total + entry.image.width * entry.image.height, 0) };
      const review = inspect(entries);
      if (step === 2) return { distinctPhotos: review.unique.length, duplicatePairs: review.duplicates, orientationWarnings: review.portraitIds };
      const bytes = contactSheet(review.unique);
      const header = new DataView(bytes.buffer);
      return {
        tiles: review.unique.length,
        dimensions: [header.getInt32(18, true), Math.abs(header.getInt32(22, true))],
        bitmapBytes: bytes.length,
        assetOrder: review.unique.map(entry => entry.id),
      };
    },
    render,
  };
})();
