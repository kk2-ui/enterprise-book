import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for the browser script regression')
class MarketObservationFrontendTests(unittest.TestCase):
    def test_existing_script_entry_supports_pages_without_new_script_tag(self):
        static = Path(__file__).resolve().parents[1] / 'static'
        script = r"""
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const directory = process.argv[1];
const appended = [];
const status = {textContent: ''};
const root = {
  isConnected: true,
  hasAttribute: name => name === 'data-observation',
  querySelector: () => status,
};
const document = {
  querySelector: () => root,
  createElement: () => ({}),
  head: {append: script => appended.push(script)},
};
const scope = vm.createContext({esc: String, document});
const existing = fs.readFileSync(path.join(directory, 'market-context.js'), 'utf8');
vm.runInContext(existing, scope);
for (const code of ['600690.SH', '690D.DE', '601857.SH']) {
  scope.company = {id: 'test-company', code};
  assert.match(vm.runInContext('marketContextShell(company)', scope), /data-observation/);
}
for (const code of ['000651.SZ', '06049.HK']) {
  scope.company = {id: 'test-company', code};
  assert.match(vm.runInContext('marketContextShell(company)', scope), /市场环境与主导力量/);
  assert.equal(vm.runInContext("withMarketObservationTab(company, [['overview', '概览']])[1][0]", scope), 'market');
  assert.match(vm.runInContext('marketObservationShell(company, {id: "published"})', scope), /data-observation-edition="published"/);
}
vm.runInContext('bindMarketContext()', scope);
assert.equal(appended.length, 1);
assert.equal(appended[0].src, '/market-observation.js');
let bound;
scope.bindMarketObservation = element => { bound = element; };
appended[0].onload();
assert.equal(bound, root);
appended[0].onerror();
assert.match(status.textContent, /脚本加载失败/);

// The current HTML also works when the new script is present before the entry point.
const current = vm.createContext({esc: String, document});
vm.runInContext(fs.readFileSync(path.join(directory, 'market-observation.js'), 'utf8'), current);
vm.runInContext(existing, current);
assert.match(vm.runInContext('marketContextShell({id:"h",code:"600690.SH"})', current), /data-observation/);
"""
        result = subprocess.run(['node', '-e', script, str(static)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
