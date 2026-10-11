const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createStore} = require('../static/browser-store.js');

function fixture() {
  const bank = {topics:[{slug:'python',label:'Python'},{slug:'rag',label:'RAG'}], questions:[
    {id:'a',prompt:'A',answer:'Answer A',content_type:'foundation',primary_topic:'python',topics:['python','rag'],stage:'S1'},
    {id:'b',prompt:'B',answer:'Answer B',content_type:'interview',primary_topic:'python',topics:['python'],stage:'S1'},
    {id:'c',prompt:'C',answer:'Answer C',content_type:'interview',primary_topic:'rag',topics:['rag'],stage:'S4'},
  ]};
  const storage = {value:null,writes:0,getItem(){return this.value;},setItem(k,v){this.value=v;this.writes++;}};
  const store = createStore(bank, storage, 'test', () => 0, () => '2026-01-01T00:00:00Z');
  const call = (url, body, method='POST') => store.request(url,{method,body:JSON.stringify(body || {})});
  const rate = (id,result) => call(`/api/questions/${id}/result`,{result},'PUT');
  return {bank,storage,store,call,rate};
}

test('scope x direction matrix, union deduplication, grouping and read-only browsing', () => {
  const {call,storage} = fixture();
  for (const [topics,content_scope,total] of [[[],'combined',3],[[],'foundation',1],[['python'],'combined',2],[['python'],'foundation',1],[['rag'],'combined',2],[['rag'],'foundation',1],[['python','rag'],'combined',3]]) {
    const r = call('/api/library/sections',{topics,content_scope});
    assert.equal(r.total,total);
    const ids = r.sections.flatMap(s=>s.groups.flatMap(g=>g.items.map(q=>q.stable_id)));
    assert.equal(new Set(ids).size,total);
  }
  assert.equal(storage.writes,0);
  assert.equal(storage.value,null);
});

test('first draw counts, wrong waits for next round, all-correct completion', () => {
  const {call,rate,storage} = fixture();
  let r = call('/api/quiz/next',{});
  assert.equal(r.question.stable_id,'a');
  assert.equal(r.question.answer,undefined);
  assert.equal(r.stats.studied,1);
  assert.equal(JSON.parse(storage.value).progress.a.last_seen_at,'2026-01-01T00:00:00Z');
  rate('a','wrong');
  r = call('/api/quiz/next',{excluded_ids:['a']});
  assert.equal(r.question.stable_id,'b');
  rate('b','correct');
  r = call('/api/quiz/next',{excluded_ids:['a','b']});
  assert.equal(r.question.stable_id,'c');
  rate('c','unrated');
  r = call('/api/quiz/next',{excluded_ids:['a','b','c']});
  assert.equal(r.question,null);
  assert.equal(r.completed,false);
  assert.deepEqual(r.progress,{total:3,correct:1,wrong:1,remaining:2});
  assert.equal(call('/api/quiz/next',{round_filter:'wrong'}).question.stable_id,'a');
  rate('a','correct');
  rate('c','correct');
  r = call('/api/quiz/next',{});
  assert.equal(r.question,null);
  assert.equal(r.completed,true);
});

test('backtracking and skipping revoke previous result; filter stats remain scoped', () => {
  const {call,rate,storage} = fixture();
  rate('a','wrong'); rate('b','correct'); rate('a','unrated');
  assert.equal(call('/api/library/sections',{result_filter:'wrong'}).total,0);
  rate('a','correct');
  const before = storage.value;
  const r = call('/api/library/sections',{topics:['rag'],result_filter:'correct'});
  assert.equal(r.total,1);
  assert.deepEqual(r.progress,{total:2,correct:1,wrong:0,remaining:1});
  assert.equal(r.stats.correct,2);
  assert.equal(storage.value,before);
});

test('refresh preserves settings/progress; new questions do not clear existing result', () => {
  const {call,rate,storage,bank} = fixture();
  call('/api/settings/selection',{topics:['python'],content_scope:'foundation'},'PUT');
  rate('a','correct');
  bank.topics.push({slug:'new'});
  bank.questions.push({...bank.questions[1],id:'new'});
  const reloaded = createStore(bank,storage,'test');
  const data = reloaded.request('/api/bootstrap');
  assert.deepEqual(data.selected_topics,['python']);
  assert.equal(data.content_scope,'foundation');
  assert.equal(data.stats.correct,1);
  assert.equal(data.stats.total,4);
  const empty = call('/api/settings/selection',{topics:[],content_scope:'combined'},'PUT');
  assert.deepEqual(empty.selected_topics,[]);
});

test('reset is global, preserves selection, and other browsers are isolated', () => {
  const {call,rate,storage,store} = fixture();
  call('/api/settings/selection',{topics:['rag'],content_scope:'foundation'},'PUT');
  call('/api/quiz/next',{}); rate('a','correct'); rate('b','wrong');
  const reset = call('/api/progress/reset');
  assert.deepEqual(reset.stats,{total:3,correct:0,wrong:0,studied:0});
  assert.deepEqual(JSON.parse(storage.value).progress,{});
  assert.deepEqual(store.request('/api/bootstrap').selected_topics,['rag']);
  rate('a','correct');
  assert.equal(fixture().store.request('/api/bootstrap').stats.correct,0);
});

test('quota errors do not claim saved progress; corrupted records are not overwritten', () => {
  const {storage,call,rate} = fixture();
  call('/api/quiz/next',{});
  const before = storage.value;
  storage.setItem = () => {throw new Error('quota');};
  assert.throws(()=>rate('a','correct'),/未保存/);
  assert.throws(()=>call('/api/progress/reset'),/未保存/);
  assert.throws(()=>call('/api/settings/selection',{topics:['rag']},'PUT'),/未保存/);
  assert.equal(storage.value,before);
  storage.value = '{bad json';
  assert.throws(()=>call('/api/quiz/next',{}),/未覆盖/);
  assert.equal(storage.value,'{bad json');
});

test('invalid inputs and unavailable answers never mutate state', () => {
  const {call,storage,store} = fixture();
  for (const args of [['/api/quiz/next',{topics:['unknown']}],['/api/quiz/next',{content_scope:'bad'}],['/api/quiz/next',{round_filter:'bad'}],['/api/library/sections',{result_filter:'bad'}],['/api/questions/a/result',{result:'bad'},'PUT']]) assert.throws(()=>call(...args));
  assert.throws(()=>store.request('/api/questions/missing/answer'));
  assert.equal(store.request('/api/questions/a/answer').answer,'Answer A');
  assert.equal(storage.writes,0);
});

test('new request re-reads shared storage rather than overwriting another tab', () => {
  const {bank,storage,rate,store} = fixture();
  const other = createStore(bank,storage,'test');
  rate('a','correct');
  other.request('/api/questions/b/result',{method:'PUT',body:JSON.stringify({result:'wrong'})});
  assert.equal(store.request('/api/bootstrap').stats.correct,1);
  assert.equal(store.request('/api/bootstrap').stats.wrong,1);
});
