/* Browser-only implementation of the UI's small API contract. No server writes. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const RESULTS = new Set(['unrated', 'correct', 'wrong']);

  function createStore(bank, storage, key, random = Math.random, now = () => new Date().toISOString()) {
    const questions = bank.questions;
    const topics = bank.topics;
    const byId = new Map(questions.map(q => [q.id, q]));
    const slugs = new Set(topics.map(t => t.slug));
    const blank = () => ({version: 1, selected_topics: [...slugs], content_scope: 'combined', progress: {}});

    function read() {
      let raw;
      try { raw = storage.getItem(key); }
      catch (_) { throw new Error('浏览器禁止读取学习记录'); }
      if (raw === null) return blank();
      let saved;
      try { saved = JSON.parse(raw); } catch (_) { throw new Error('浏览器学习记录损坏；未覆盖原记录'); }
      if (saved?.version !== 1 || !Array.isArray(saved.selected_topics) ||
          !['foundation', 'combined'].includes(saved.content_scope) ||
          !saved.progress || typeof saved.progress !== 'object' || Array.isArray(saved.progress)) {
        throw new Error('浏览器学习记录格式不兼容；未覆盖原记录');
      }
      const result = blank();
      result.selected_topics = [...new Set(saved.selected_topics.filter(s => slugs.has(s)))];
      result.content_scope = saved.content_scope;
      // Only stable IDs in this bank are counted. Adding questions never resets old IDs.
      for (const q of questions) {
        const p = saved.progress[q.id];
        if (!p) continue;
        if (!RESULTS.has(p.result) || !Number.isSafeInteger(p.seen_count) || p.seen_count < 0 ||
            !(p.last_seen_at === null || typeof p.last_seen_at === 'string')) {
          throw new Error('浏览器练习记录格式错误；未覆盖原记录');
        }
        result.progress[q.id] = {...p};
      }
      return result;
    }

    function write(saved) {
      try { storage.setItem(key, JSON.stringify(saved)); }
      catch (_) { throw new Error('无法保存学习记录：浏览器存储被禁用或空间不足，本次操作未保存'); }
    }
    const entry = (saved, id) => saved.progress[id] || {result:'unrated', seen_count:0, last_seen_at:null};
    function pool(payload) {
      const selected = payload.topics || [];
      const scope = payload.content_scope || 'combined';
      if (!Array.isArray(selected) || selected.some(s => !slugs.has(s))) throw new Error('无效方向');
      if (!['foundation','combined'].includes(scope)) throw new Error('无效内容范围');
      return questions.filter(q => (scope === 'combined' || q.content_type === 'foundation') &&
        (!selected.length || q.topics.some(s => selected.includes(s))));
    }
    function stats(saved, rows = questions) {
      return {total: rows.length,
        correct: rows.filter(q => entry(saved,q.id).result === 'correct').length,
        wrong: rows.filter(q => entry(saved,q.id).result === 'wrong').length,
        studied: rows.filter(q => entry(saved,q.id).seen_count > 0).length};
    }
    function progress(saved, rows) {
      const s = stats(saved, rows);
      return {total:s.total, correct:s.correct, wrong:s.wrong, remaining:s.total-s.correct};
    }
    const item = (q, saved) => {
      const {id, ...rest} = q;
      return {...rest, stable_id:id, result:entry(saved,id).result};
    };

    // Reads are side-effect free. Mutations persist before returning success to UI.
    function request(url, options = {}) {
      const saved = read();
      const p = options.body ? JSON.parse(options.body) : {};
      const method = options.method || 'GET';
      if (url === '/api/bootstrap' && method === 'GET') {
        return {topics:topics.map(t => {
          const rows = questions.filter(q => q.topics.includes(t.slug));
          return {...t,question_count:rows.length,
            foundation_count:rows.filter(q => q.content_type === 'foundation').length,
            interview_count:rows.filter(q => q.content_type === 'interview').length};
        }),selected_topics:saved.selected_topics,content_scope:saved.content_scope,stats:stats(saved)};
      }
      if (url === '/api/settings/selection' && method === 'PUT') {
        pool(p);
        saved.selected_topics = [...new Set(p.topics || [])];
        saved.content_scope = p.content_scope || 'combined';
        write(saved);
        return {selected_topics:saved.selected_topics,content_scope:saved.content_scope};
      }
      if (url === '/api/progress/reset' && method === 'POST') {
        saved.progress = {};
        write(saved);
        return {ok:true,stats:stats(saved)};
      }
      const match = url.match(/^\/api\/questions\/([^/]+)\/(answer|result)$/);
      if (match) {
        const q = byId.get(decodeURIComponent(match[1]));
        if (!q) throw new Error('题目不存在');
        if (match[2] === 'answer' && method === 'GET') return {answer:q.answer,source_name:q.source_name,source_ref:q.source_ref};
        if (match[2] === 'result' && method === 'PUT') {
          const rows = pool(p);
          if (!RESULTS.has(p.result)) throw new Error('无效评价');
          saved.progress[q.id] = {...entry(saved,q.id),result:p.result};
          write(saved);
          return {stats:stats(saved),progress:progress(saved,rows)};
        }
      }
      if (url === '/api/quiz/next' && method === 'POST') {
        const rows = pool(p);
        const filter = p.round_filter || 'remaining';
        if (!['remaining','wrong'].includes(filter)) throw new Error('无效复习范围');
        const excluded = new Set(p.excluded_ids || []);
        const available = rows.filter(q => !excluded.has(q.id) && entry(saved,q.id).result !== 'correct' &&
          (filter !== 'wrong' || entry(saved,q.id).result === 'wrong'));
        let candidates = available.filter(q => q.id !== p.previous_id);
        if (!candidates.length) candidates = available;
        let question = null;
        if (candidates.length) {
          const chosen = candidates[Math.floor(random() * candidates.length)];
          const prev = entry(saved,chosen.id);
          saved.progress[chosen.id] = {...prev,seen_count:prev.seen_count+1,last_seen_at:now()};
          write(saved);
          question = item(chosen,saved);
          delete question.answer;
          Object.assign(question, {cycle:prev.seen_count+1,pool_size:available.length,remaining_in_cycle:available.length});
        }
        const scoped = progress(saved,rows);
        return {question,stats:stats(saved),progress:scoped,completed:scoped.total > 0 && scoped.remaining === 0};
      }
      if (url === '/api/library/sections' && method === 'POST') {
        const rows = pool(p);
        const filter = p.result_filter || 'all';
        if (!['all','correct','wrong'].includes(filter)) throw new Error('无效评价筛选');
        const filtered = rows.filter(q => filter === 'all' || entry(saved,q.id).result === filter)
          .sort((a,b) => a.stage < b.stage ? -1 : a.stage > b.stage ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
        const sections = topics.map(topic => {
          const groups = ['foundation','interview'].map(type => {
            const items = filtered.filter(q => q.primary_topic === topic.slug && q.content_type === type).map(q => item(q,saved));
            return {content_type:type,label:type === 'foundation' ? '基础知识' : '面试题',anchor_id:`section-${topic.slug}-${type}`,count:items.length,items};
          }).filter(g => g.count);
          return {topic,count:groups.reduce((sum,g) => sum+g.count,0),groups};
        }).filter(s => s.count);
        return {sections,total:filtered.length,content_scope:p.content_scope || 'combined',selected_topics:p.topics || [],stats:stats(saved),progress:progress(saved,rows)};
      }
      throw new Error('网页版不支持此操作');
    }
    return {request:(...args) => clone(request(...args))};
  }

  let storePromise;
  async function request(url, options = {}) {
    const config = root.InterviewStaticConfig;
    if (!storePromise) {
      storePromise = (async () => {
        const response = await fetch(config.bankUrl);
        if (!response.ok) throw new Error(`题库文件读取失败（${response.status}）`);
        return createStore(await response.json(), root.localStorage, config.storageKey);
      })().catch(error => { storePromise = null; throw error; });
    }
    const store = await storePromise;
    const act = () => store.request(url, options);
    // HTTPS browsers with Web Locks serialize read-modify-write across tabs.
    if (root.navigator?.locks) return root.navigator.locks.request(config.storageKey, act);
    return act();
  }
  const api = {createStore,request};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.InterviewBrowser = api;
})(globalThis);
