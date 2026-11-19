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

    def test_market_explanation_uses_comparable_dates_and_handles_late_disclosure(self):
        module = Path(__file__).resolve().parents[1] / 'static' / 'market-driver-chart.js'
        script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8')
  .replace('export function renderDriverChart(', 'function renderDriverChart(');
const render = vm.runInNewContext(source + '\nbuildClueCardsHtml');
const date = day => '2026-11-' + String(day).padStart(2, '0');
const days = [2, 3, 4, 5, 6, 9, 10, 11, 12, 13];
const stock = [100, 102, 104, 110, 108, 100, 90, 95, 100, 105];
const bench = [100, 101, 102, 103, 104, 105, 110, 107, 102, 101];
const model = {
  profile: { companyName: '测试公司', isPoly: false },
  benchMeta: { label: '市场基准' },
  macroMeta: { loaded: true, label: '行业数据', unit: '%' },
  macroSeries: [{ period: '2026-10', published: date(12), value: -4.2, url: '' }],
  microSeriesList: [{ label: '测试财报', unit: '亿元', points: [
    { period: '2026-09-30', published: date(14), value: 22, url: '' },
  ] }],
  stockWin: days.map((day, i) => ({ date: date(day), close: stock[i] })),
  benchMap: new Map(days.slice(1).map((day, i) => [date(day), bench[i + 1]])),
  dxySeries: days.map((day, i) => ({ date: date(day), close: 100 + i })),
};
const late = render(model, date(15));
assert.match(late, /2026-11-03/);
assert.match(late, /2026-11-14/);
assert.match(late, /晚于/);
assert.match(late, /百分点/);
assert.doesNotMatch(late, /2026-11-02/);
const early = render(model, date(10));
assert.doesNotMatch(early, /2026-11-1[1-5]/);
assert.match(early, /2026-11-10/);
model.benchMap.clear();
const onlyStock = render(model, date(10));
assert.match(onlyStock, /不足|暂无|无法/);
assert.match(onlyStock, /10\.00%/);
"""
        result = subprocess.run(['node', '-e', script, str(module)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
