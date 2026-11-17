/* Shared, DOM-free search and fair discovery. */
(function(root){
const norm=s=>String(s||'').normalize('NFKC').toLocaleLowerCase('ja').replace(/\s+/g,' ').trim();
function shuffle(rows,rng=Math.random){const a=[...rows];for(let i=a.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
function balanced(rows){const buckets=new Map();for(const a of rows){if(!buckets.has(a.author_id))buckets.set(a.author_id,[]);buckets.get(a.author_id).push(a)}const b=[...buckets.values()];const out=[];let index=0;while(out.length<rows.length){for(const a of b)if(a[index])out.push(a[index]);index++}return out}
function filter(rows,f){const terms=norm(f.q).split(' ').filter(Boolean);return rows.filter(a=>terms.every(t=>a.search.includes(t))&&(!f.category||a.category_ids.includes(f.category))&&(!f.group||a.group_ids.includes(f.group))&&(!f.topic||a.topic_ids.includes(f.topic))&&(!f.era||Math.floor(Number(a.published_at.slice(0,4))/10)*10===Number(f.era))&&(!f.author||a.author_id===f.author))}
function draw(rows,rng=Math.random){const ids=[...new Set(rows.map(a=>a.author_id))];if(!ids.length)return null;const id=ids[Math.floor(rng()*ids.length)];const own=rows.filter(a=>a.author_id===id);return own[Math.floor(rng()*own.length)]}
const api={norm,shuffle,balanced,filter,draw};root.AntennaCore=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
