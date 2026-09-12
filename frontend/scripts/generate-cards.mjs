// Rebuild the 52 approved, font-independent card images: node scripts/generate-cards.mjs
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';

const ranks = JSON.parse(readFileSync(new URL('./card-ranks.json', import.meta.url)));
const destination = new URL('../src/assets/clean-cards/', import.meta.url);
mkdirSync(destination, { recursive: true });
const suits = {
  hearts: 'M50 94C40 79 3 55 3 30C3 3 36 -3 50 19C64 -3 97 3 97 30C97 55 60 79 50 94Z',
  diamonds: 'M50 0L98 50L50 100L2 50Z',
  spades: 'M50 0C39 17 3 43 3 65C3 88 31 96 44 78C43 89 39 96 34 100H66C61 96 57 89 56 78C69 96 97 88 97 65C97 43 61 17 50 0Z',
  clubs: 'M50 0C24 0 19 30 34 42C10 31 -4 51 4 72C10 90 32 92 44 76C43 88 39 96 33 100H67C61 96 57 88 56 76C68 92 90 90 96 72C104 51 90 31 66 42C81 30 76 0 50 0Z',
};
const names = { A: 'ace', J: 'jack', Q: 'queen', K: 'king' };
for (const [suit, path] of Object.entries(suits)) {
  const color = ['hearts', 'diamonds'].includes(suit) ? '#df292e' : '#252525';
  for (const [rank, glyph] of Object.entries(ranks)) {
    const [x0, y0, x1, y1] = glyph.bounds;
    // Consistent cap height; Q's tail extends below the shared baseline.
    const scale = 106 / -y0;
    const width = (x1 - x0) * scale;
    const sx = Math.min(scale, 137 / (x1 - x0));
    const tx = 42 - x0 * sx;
    const ty = 49 - y0 * scale;
    if (width <= 0 || (y1 - y0) * scale > 145) throw new Error(`Invalid rank: ${rank}`);
    const name = `${names[rank] || rank}_of_${suit}`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="250" height="350" viewBox="0 0 250 350"><title>${name.replaceAll('_', ' ')}</title><rect width="250" height="350" rx="12" fill="#fff"/><g fill="${color}"><path d="${glyph.path}" transform="matrix(${sx.toFixed(6)} 0 0 ${scale.toFixed(6)} ${tx.toFixed(3)} ${ty.toFixed(3)})"/><path d="${path}" transform="translate(103 180) scale(1.15)"/></g></svg>`;
    writeFileSync(new URL(`${name}.svg`, destination), svg + '\n');
  }
}
console.log('Generated 52 clean card faces.');
