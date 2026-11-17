const assert=require('node:assert/strict');const C=require('../web/core.js');
const a={title:'a',author_id:'a',published_at:'2014-01-01',category_ids:['jp-female'],group_ids:['perfume'],topic_ids:['live'],search:C.norm('Perfume ぐるんぐるん splicom')};const b={...a,author_id:'b',published_at:'2026-01-01',group_ids:['milk'],search:C.norm('Ｍ！ＬＫ 感想 writer')};
assert.equal(C.filter([a,b],{q:'Ｍ！ＬＫ'}).length,1);assert.equal(C.filter([a,b],{era:'2010'}).length,1);assert.equal(C.filter([a,b],{group:'perfume',q:'splicom'}).length,1);assert.equal(C.filter([a,b],{q:'not found'}).length,0);
assert.equal(C.draw([a,a,a,b],()=>0.75).author_id,'b');assert.equal(C.draw([]),null);assert.deepEqual(C.balanced([a,a,b]).map(x=>x.author_id),['a','b','a']);
const rows=Array.from({length:30000},(_,i)=>({...a,id:String(i),author_id:'w'+(i%1000)}));
const start=performance.now();assert.equal(C.filter(rows,{q:'Perfume',group:'perfume',era:'2010'}).length,30000);assert.equal(C.balanced(rows).length,30000);const elapsed=performance.now()-start;
console.log(`Search/discovery assertions passed; 30,000 metadata rows filter + fair interleave: ${elapsed.toFixed(1)} ms (Node, not mobile browser).`);
