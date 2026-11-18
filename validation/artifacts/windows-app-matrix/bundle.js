'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function assertSubset(actual, expected, label) {
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), label + ' should be an array');
    assert.equal(actual.length, expected.length, label + ' array length');
    expected.forEach((item, index) => assertSubset(actual[index], item, label + '[' + index + ']'));
    return;
  }
  if (expected !== null && typeof expected === 'object') {
    assert.ok(actual !== null && typeof actual === 'object', label + ' should be an object');
    for (const [key, item] of Object.entries(expected)) {
      assert.ok(Object.hasOwn(actual, key), label + ' is missing ' + key);
      assertSubset(actual[key], item, label + '.' + key);
    }
    return;
  }
  assert.equal(actual, expected, label);
}

function readCase(directory, filename) {
  const source = fs.readFileSync(path.join(directory, filename), 'utf8');
  const sandbox = vm.createContext({ window: {}, TextEncoder, TextDecoder, URL, URLSearchParams, atob, btoa });
  vm.runInContext(source, sandbox, { filename, timeout: 500 });
  const spec = sandbox.window.caseDefinition;
  const id = path.basename(filename, '.js');
  assert.equal(spec?.id, id, 'Case ID must match file name');
  for (const field of ['title', 'kicker', 'scenario', 'layout', 'accent', 'surface', 'text']) {
    assert.ok(typeof spec[field] === 'string' && spec[field].trim(), id + ': missing ' + field);
  }
  assert.equal(spec.actions.length, 3, id + ': expected three action labels');
  assert.equal(spec.expected.length, 3, id + ': expected three sets of assertions');
  vm.runInContext(String.raw`
    const definition = window.caseDefinition;
    const initialView = definition.render(0, null);
    let prior = null;
    const verifiedPhases = [];
    for (let step = 1; step <= 3; step++) {
      const actual = definition.run(step, prior);
      verifiedPhases.push({ actual, html: definition.render(step, actual) });
      prior = actual;
    }
  `, sandbox, { filename: filename + ' validation', timeout: 1000 });
  assert.ok(vm.runInContext('typeof initialView === "string" && initialView.trim().length > 0', sandbox), id + ': empty initial view');
  const verified = vm.runInContext('verifiedPhases', sandbox);
  verified.forEach(({ actual, html }, index) => {
    assert.ok(actual !== null && typeof actual === 'object', id + ': use JSON object results');
    assert.ok(typeof html === 'string' && html.trim(), id + ': empty phase view');
    const json = JSON.parse(JSON.stringify(actual));
    assertSubset(json, spec.expected[index], id + ' action ' + (index + 1));
  });
  const { title, kicker, scenario, actions, expected, layout } = spec;
  return { source, registry: { id, title, kicker, scenario, actions, expected, layout } };
}

function main() {
  const output = process.argv[2];
  if (!output) throw new Error('Usage: node bundle.js <outputDirectory>');
  const directory = path.join(__dirname, 'cases');
  const template = fs.readFileSync(path.join(__dirname, 'runtime.html'), 'utf8');
  const filenames = fs.readdirSync(directory).filter((name) => /^\d\d\.js$/.test(name)).sort();
  if (!filenames.length) throw new Error('No application cases are available');
  const cases = filenames.map((filename) => readCase(directory, filename));
  fs.mkdirSync(output, { recursive: true });
  for (const { registry, source } of cases) {
    const inlineSource = source.replace(/<\/script\b/gi, '<\\/script');
    const html = template.replace('/* CASE_SCRIPT */', () => inlineSource);
    fs.writeFileSync(path.join(output, registry.id + '.html'), html, 'utf8');
  }
  fs.writeFileSync(path.join(output, 'cases.json'), JSON.stringify(cases.map((item) => item.registry), null, 2) + '\n', 'utf8');
  console.log('Bundled ' + cases.length + ' apps with validated workflow results.');
}

if (require.main === module) main();
