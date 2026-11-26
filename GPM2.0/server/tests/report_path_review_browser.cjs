// Optional offline UI acceptance for report_path_review_fixture.py. No npm dependencies.
// CHROME=/path/to/chromium node report_path_review_browser.cjs /path/to/fixture-output
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const chrome = process.env.CHROME, root = process.argv[2];
if (!root || !chrome) throw Error('Set CHROME and pass the review fixture directory');
const pages = [path.join(root, 'project/06_report/report.html'), path.join(root, 'lgz/lgz-only.html')];
pages.forEach(p => assert.ok(fs.statSync(p).isFile()));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cgat-offline-review-'));
const browser = spawn(chrome, ['--headless', '--disable-gpu', '--disable-background-networking',
  ...(process.env.CGAT_TEST_CHROME_NO_SANDBOX === '1' ? ['--no-sandbox'] : []),
  `--user-data-dir=${profile}`, '--remote-debugging-pipe', 'about:blank'], {stdio:['ignore','ignore','inherit','pipe','pipe']});
const pending = new Map(), errors = [];
let next = 0, buffer = '';
browser.stdio[4].setEncoding('utf8');
browser.stdio[4].on('data', data => {
  buffer += data;
  while (buffer.includes('\0')) {
    const at = buffer.indexOf('\0'), r = JSON.parse(buffer.slice(0, at)); buffer = buffer.slice(at+1);
    if (r.method === 'Runtime.exceptionThrown') errors.push(r.params.exceptionDetails.text);
    if (r.method === 'Network.requestWillBeSent' && /^(https?:|wss?:)/i.test(r.params.request.url)) errors.push('non-local request');
    if (pending.has(r.id)) {const [ok,fail] = pending.get(r.id); pending.delete(r.id); r.error ? fail(Error(r.error.message)) : ok(r.result);}
  }
});
function call(method,params={},sessionId) {return new Promise((ok,fail)=>{
  const id=++next; pending.set(id,[ok,fail]); browser.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');
});}
browser.on('exit',()=>{for(const [,fail] of pending.values())fail(Error('browser exited'));pending.clear();fs.rmSync(profile,{recursive:true,force:true});});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function check(){
  const {targetInfos}=await call('Target.getTargets');
  const {sessionId:s}=await call('Target.attachToTarget',{targetId:targetInfos.find(t=>t.type==='page').targetId,flatten:true});
  await call('Network.enable',{},s);await call('Network.setBlockedURLs',{urls:['http://*','https://*','ws://*','wss://*']},s);await call('Runtime.enable',{},s);
  async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true},s);if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
  async function open(file,css){await call('Page.navigate',{url:pathToFileURL(path.resolve(file)).href},s);for(let i=0;i<100;i++){if(await evaluate(`!!document.querySelector(${JSON.stringify(css)})`))return;await delay(30);}throw Error('missing '+css);}
  async function click(css){await evaluate(`document.querySelector(${JSON.stringify(css)}).click()`);}
  async function close(){await click('[data-story-close]');await delay(30);}
  await open(pages[0],'#final-path [data-copy]');
  assert.equal(await evaluate("document.querySelectorAll('#final-path details[open]').length"),0);
  {
    const btn='#final-path summary [data-story-open]';const file=await evaluate("document.querySelector('#final-path [data-copy]').dataset.copy");
    assert.ok(file.endsWith('.degap.fa')&&fs.statSync(file).isFile());await click(btn);
    assert.equal(await evaluate("document.querySelector('dialog').matches(':modal')"),true);assert.ok((await evaluate("document.querySelector('dialog [aria-pressed=true]').textContent")).startsWith('DEGAP'));await close();assert.equal(await evaluate(`document.activeElement===document.querySelector('${btn}')`),true);
  }
  const panel='[data-manual-batch]:not([hidden])';
  for(const version of ['v1','v2']){
    await evaluate(`(()=>{const el=document.querySelector('[data-manual-select]');el.selectedIndex=Array.from(el.options).findIndex((_,i)=>document.querySelector('[data-manual-batch="'+i+'"]').textContent.includes('new-chr-${version}'));el.dispatchEvent(new Event('change'))})()`);
    await click(panel+' summary [data-manual-gap]');assert.equal(await evaluate("document.querySelectorAll('dialog .gap-tools button').length"),3);
    if(version==='v1'){assert.ok((await evaluate("document.querySelector('dialog [aria-pressed=true]').textContent")).includes('Selected'));await evaluate("document.querySelectorAll('dialog .gap-tools button')[1].click()");assert.ok((await evaluate("document.querySelector('dialog').textContent")).includes('not selected'));}
    assert.equal(await evaluate("document.querySelectorAll('dialog svg').length"),1);await close();
  }
  await open(pages[1],'.tel-end');assert.equal(await evaluate("document.querySelector('#final-path h2 small').textContent"),'07');assert.equal(await evaluate("document.querySelectorAll('#auto-refinement,#manual-refinement').length"),0);
  for(const width of [1250,390]){await call('Emulation.setDeviceMetricsOverride',{width,height:880,mobile:false,deviceScaleFactor:1},s);const [pageWidth,rowHeight]=await evaluate("[document.documentElement.scrollWidth,document.querySelector('#final-path summary').getBoundingClientRect().height]");assert.ok(pageWidth<=width+1,`page overflows ${width}px`);assert.ok(rowHeight<48,'collapsed row not compact');}
  for(const [mark,hasAlignment] of [['TEL',true],['○',false]]){await evaluate(`Array.from(document.querySelectorAll('.tel-end')).find(b=>b.textContent==='${mark}').click()`);assert.equal(await evaluate("document.querySelectorAll('dialog polygon').length>0"),hasAlignment);await close();}
  assert.deepEqual(errors,[]);console.log('PASS: offline versions, final FASTAs and gap selection, isolated manual batches, endpoint evidence and compact rows at 390/1250 px.');
}
const timer=setTimeout(()=>{console.error('Browser check timed out');process.exitCode=1;browser.kill();},45000);
check().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{clearTimeout(timer);browser.kill();});
