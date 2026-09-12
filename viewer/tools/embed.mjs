/**
 * Re-embeds skins/ and traces/ into index.html and gallery.html.
 *
 * The pages ship with their data inlined so they work from a file:// URL with
 * no server. That means adding a skin needs this run once. Trying a skin does
 * not — drag the JSON onto either page.
 *
 *   node tools/embed.mjs
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const readDir = dir =>
  readdirSync(join(root, dir))
    .filter(f => f.endsWith('.json'))
    .map(f => JSON.parse(readFileSync(join(root, dir, f), 'utf8')));

const skins = Object.fromEntries(readDir('skins').map(s => [s.name, s]));
const traces = Object.fromEntries(
  readdirSync(join(root, 'traces'))
    .filter(f => f.endsWith('.json'))
    .map(f => [f.slice(0, -5), JSON.parse(readFileSync(join(root, 'traces', f), 'utf8'))]),
);

const swap = (src, decl, value) => {
  const re = new RegExp(`(const ${decl}\\s*=\\s*)\\{[\\s\\S]*?\\};`);
  if (!re.test(src)) throw new Error(`could not find "const ${decl} = {...};"`);
  return src.replace(re, (_m, head) => head + JSON.stringify(value) + ';');
};

for (const [file, decls] of [
  ['index.html', { TRACES: traces, SKINS: skins }],
  ['gallery.html', { SKINS: skins }],
]) {
  let src = readFileSync(join(root, file), 'utf8');
  for (const [decl, value] of Object.entries(decls)) src = swap(src, decl, value);
  writeFileSync(join(root, file), src);
  console.log(`${file}: ${Object.keys(skins).length} skins, ${Object.keys(traces).length} traces`);
}
