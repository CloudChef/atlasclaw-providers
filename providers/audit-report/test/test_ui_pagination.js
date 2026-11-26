const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const appPath = path.join(__dirname, '..', 'ui', 'app.js');
const source = fs.readFileSync(appPath, 'utf8');
const signature = 'async function fetchAllDocuments()';
const start = source.indexOf(signature);
assert.notEqual(start, -1, 'fetchAllDocuments must remain a standalone helper');
const open = source.indexOf('{', start);
let depth = 0;
let end = -1;
for (let index = open; index < source.length; index += 1) {
  if (source[index] === '{') depth += 1;
  if (source[index] === '}') depth -= 1;
  if (depth === 0) {
    end = index + 1;
    break;
  }
}
assert.notEqual(end, -1, 'fetchAllDocuments must have a complete body');
const helperSource = `return (${source.slice(start, end)});`;

test('document loader fetches every page in page-size batches', async () => {
  const allItems = Array.from({ length: 237 }, (_, index) => ({ id: `doc-${index + 1}` }));
  const calls = [];
  const api = async query => {
    calls.push(query);
    const page = Number(new URLSearchParams(query.split('?')[1]).get('page'));
    const pageSize = Number(new URLSearchParams(query.split('?')[1]).get('page_size'));
    const offset = (page - 1) * pageSize;
    return { items: allItems.slice(offset, offset + pageSize), total: allItems.length, page, page_size: pageSize };
  };
  const load = new Function('api', helperSource)(api);

  const result = await load();

  assert.equal(result.length, 237);
  assert.equal(result.at(-1).id, 'doc-237');
  assert.deepEqual(calls, [
    '/documents?page=1&page_size=100',
    '/documents?page=2&page_size=100',
    '/documents?page=3&page_size=100',
  ]);
});

test('pagination failure rejects before replacing the prior document list', async () => {
  const previousItems = [{ id: 'existing' }];
  const api = async query => {
    if (query.includes('page=1')) return { items: Array(100).fill({}), total: 101 };
    throw new Error('page unavailable');
  };
  const load = new Function('api', helperSource)(api);
  let displayedItems = previousItems;

  try {
    displayedItems = await load();
  } catch (_) {
    // The caller assigns only after all pages resolve, preserving prior state.
  }

  assert.equal(displayedItems, previousItems);
});
