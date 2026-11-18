(() => {
  const width = 8;
  const height = 6;
  const source = [
    { name: 'Search', glyph: '⌕', x: 0, y: 0, w: 3, h: 3, color: '#f5bc42' },
    { name: 'Notify', glyph: '◈', x: 2, y: 1, w: 3, h: 3, color: '#fd8ab4' },
    { name: 'Launch', glyph: '↗', x: 5, y: 1, w: 2, h: 2, color: '#81ded5' },
    { name: 'Menu', glyph: '≡', x: 0, y: 4, w: 2, h: 2, color: '#ff8964' },
    { name: 'Confirm', glyph: '✓', x: 6, y: 4, w: 2, h: 2, color: '#c4b0ff' },
  ];

  function check(sprites) {
    const grid = new Map();
    let overlaps = 0;
    let outOfBounds = 0;
    for (const sprite of sprites) {
      for (let row = sprite.y; row < sprite.y + sprite.h; row++) {
        for (let column = sprite.x; column < sprite.x + sprite.w; column++) {
          if (column < 0 || column >= width || row < 0 || row >= height) {
            outOfBounds++;
            continue;
          }
          const cell = row * width + column;
          if (grid.has(cell)) overlaps++;
          grid.set(cell, sprite.name);
        }
      }
    }
    return { overlaps, outOfBounds, usedCells: grid.size };
  }

  function repack() {
    const sprites = [];
    for (const glyph of source) {
      let candidate;
      for (let y = 0; y <= height - glyph.h && !candidate; y++) {
        for (let x = 0; x <= width - glyph.w && !candidate; x++) {
          const trial = { ...glyph, x, y };
          if (!check([...sprites, trial]).overlaps) candidate = trial;
        }
      }
      if (!candidate) throw new Error('Atlas capacity exceeded for ' + glyph.name);
      sprites.push(candidate);
    }
    return sprites;
  }

  function render(step, result) {
    const sprites = step === 3 ? result.sprites : source;
    const collision = step === 2 ? '<div class="atlas-collision" aria-label="overlap" style="--x:2;--y:1"></div>' : '';
    const tileHtml = sprites.map(({ name, glyph, x, y, w, h, color }) => '<div class="atlas-tile" style="--x:' + x + ';--y:' + y +
      ';--w:' + w + ';--h:' + h + ';background:' + color + '"><b>' + glyph + '</b><span>' + name + '</span></div>').join('');
    const rows = sprites.map(({ name, x, y }) => '<li>' + name + '<small>(' + x + ', ' + y + ')</small></li>').join('');
    const note = step < 2 ? 'Packed positions on an 8 × 6 grid' : step === 2 ? result.overlaps + ' cells collide' : 'Zero collisions · 5 sprites';
    return '<div class="atlas"><div class="atlas-sheet">' + tileHtml + collision + '</div><div class="atlas-detail"><small>SPRITE SHEET / UI-005</small>' +
      '<h2>Toolbar glyphs</h2><p>' + note + '</p><ul>' + rows + '</ul></div></div>';
  }

  window.caseDefinition = {
    id: '08',
    title: 'Glyph Atlas',
    kicker: 'Icon production',
    scenario: 'Reject a sprite sheet with an overlap and regenerate a compact texture manifest.',
    layout: 'canvas',
    accent: '#eaa855',
    surface: '#fff7ec',
    text: '#3a291c',
    actions: ['Load toolbar icons', 'Find overlapping cells', 'Repack and build manifest'],
    expected: [
      { spriteCount: 5, width: 8, height: 6 },
      { overlaps: 2, outOfBounds: 0, usedCells: 28, releaseAllowed: false },
      { overlaps: 0, outOfBounds: 0, usedCells: 30, releaseAllowed: true },
    ],
    style: '.atlas{display:grid;grid-template-columns:385px 1fr;gap:36px;padding:19px 30px;background:#fff7ec;color:#3a291c;border-radius:12px}.atlas-sheet{position:relative;width:368px;height:276px;background:linear-gradient(90deg,#6c513937 1px,transparent 1px),linear-gradient(#6c513937 1px,transparent 1px),#ffe5c6;background-size:46px 46px;border:1px solid #bb8a59;border-radius:8px;overflow:hidden}.atlas-tile,.atlas-collision{position:absolute;left:calc(var(--x) * 46px);top:calc(var(--y) * 46px);width:calc(var(--w) * 46px);height:calc(var(--h) * 46px);box-sizing:border-box}.atlas-tile{display:grid;align-content:center;justify-items:center;border:2px solid #49332b8c;border-radius:8px;color:#382c21}.atlas-tile b{font:700 35px Segoe UI Symbol,sans-serif}.atlas-tile span{font-size:12px;font-weight:650}.atlas-collision{width:46px;height:92px;outline:2px dashed #b5242c;outline-offset:-2px;background:repeating-linear-gradient(135deg,#c01d3450 0 4px,transparent 4px 8px)}.atlas-detail h2{font:700 35px Georgia,serif;margin:6px 0 10px}.atlas-detail small{color:#745337}.atlas-detail p{font-weight:650}.atlas-detail ul{list-style:none;padding:0;max-width:260px}.atlas-detail li{border-bottom:1px solid #e6cbb3;padding:6px 0}.atlas-detail li small{float:right;font-family:Consolas,monospace}',
    run(step) {
      const shape = { spriteCount: source.length, width, height };
      if (step === 1) return shape;
      const sprites = step === 3 ? repack() : source;
      const collisions = check(sprites);
      return { ...shape, ...collisions, sprites, releaseAllowed: collisions.overlaps === 0 && collisions.outOfBounds === 0 };
    },
    render,
  };
})();
