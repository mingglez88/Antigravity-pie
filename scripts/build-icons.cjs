// Deterministic vector source -> UI PNG and Windows multi-resolution ICO.
const { Resvg } = require('@resvg/resvg-js');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', 'assets');
const svg = fs.readFileSync(path.join(root, 'launcher-icon.svg'), 'utf8');
const sizes = [16, 24, 32, 48, 64, 128, 256];
const pngs = sizes.map(size => new Resvg(svg, { fitTo: { mode: 'width', value: size } }).render().asPng());
const header = Buffer.alloc(6 + 16 * sizes.length);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
for (let i = 0; i < sizes.length; i++) {
  const start = 6 + 16 * i;
  header[start] = header[start + 1] = sizes[i] === 256 ? 0 : sizes[i];
  header.writeUInt16LE(1, start + 4);
  header.writeUInt16LE(32, start + 6);
  header.writeUInt32LE(pngs[i].length, start + 8);
  header.writeUInt32LE(offset, start + 12);
  offset += pngs[i].length;
}
fs.writeFileSync(path.join(root, 'launcher-icon.ico'), Buffer.concat([header, ...pngs]));
fs.writeFileSync(path.join(root, 'launcher-icon.png'), pngs.at(-1));
fs.writeFileSync(path.join(root, 'launcher-icon-48.png'), pngs[sizes.indexOf(48)]);
console.log('Generated ICO sizes: ' + sizes.join(', '));
