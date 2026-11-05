const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { Resvg } = require('@resvg/resvg-js');
test('Windows icon contains the exact rendered vector at every supported size', () => {
  const root = path.join(__dirname, '../assets');
  const source = fs.readFileSync(path.join(root, 'launcher-icon.svg'), 'utf8');
  const ico = fs.readFileSync(path.join(root, 'launcher-icon.ico'));
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  assert.equal(ico.readUInt16LE(2), 1);
  assert.equal(ico.readUInt16LE(4), sizes.length);
  for (let i = 0; i < sizes.length; i++) {
    const offset = 6 + i * 16;
    assert.equal(ico[offset] || 256, sizes[i]);
    const start = ico.readUInt32LE(offset + 12);
    const length = ico.readUInt32LE(offset + 8);
    const rendered = new Resvg(source, {fitTo:{mode:'width',value:sizes[i]}}).render().asPng();
    assert.deepEqual(ico.subarray(start, start + length), rendered);
    if (sizes[i] === 48) assert.deepEqual(fs.readFileSync(path.join(root, 'launcher-icon-48.png')), rendered);
  }
});
