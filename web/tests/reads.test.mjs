import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

// Execute the real TypeScript helper using the existing compiler, without
// adding a browser or a test framework to the production dependencies.
const source = await readFile(new URL('../src/api/reads.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext } }).outputText;
const { readShared, invalidateReads } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('overlapping reads share work; completed live reads remain fresh', async () => {
  invalidateReads();
  let calls = 0, resolve;
  const load = () => { calls++; return new Promise(done => { resolve = done; }); };
  const first = readShared('products', load);
  assert.equal(readShared('products', load), first);
  resolve(['product']);
  assert.deepEqual(await first, ['product']);
  const second = readShared('products', load);
  assert.equal(calls, 2);
  resolve(['new product']);
  await second;
});

test('brief cache expires and mutations invalidate it', async () => {
  invalidateReads();
  const originalNow = Date.now;
  let now = 100, calls = 0;
  Date.now = () => now;
  try {
    const load = async () => ++calls;
    assert.equal(await readShared('products', load, 5000), 1);
    assert.equal(await readShared('products', load, 5000), 1);
    now += 5001;
    assert.equal(await readShared('products', load, 5000), 2);
    invalidateReads();
    assert.equal(await readShared('products', load, 5000), 3);
  } finally { Date.now = originalNow; }
});

test('a response started before a mutation cannot overwrite the fresh cache', async () => {
  invalidateReads();
  let finishOld;
  const old = readShared('products', () => new Promise(done => { finishOld = done; }), 5000);
  invalidateReads();
  assert.equal(await readShared('products', async () => 'new', 5000), 'new');
  finishOld('old');
  await old;
  assert.equal(await readShared('products', async () => 'wrong', 5000), 'new');
});

test('failed reads can retry; different filters never share a result', async () => {
  invalidateReads();
  await assert.rejects(readShared('failed', async () => { throw new Error('offline'); }));
  assert.equal(await readShared('failed', async () => 'retry'), 'retry');
  const values = await Promise.all([
    readShared('history?page=1', async () => 1), readShared('history?page=2', async () => 2),
  ]);
  assert.deepEqual(values, [1, 2]);
});
