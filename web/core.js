/* Shared, DOM-free search and fair discovery. */
(function(root){
const norm=s=>String(s||'').normalize('NFKC').toLocaleLowerCase('ja').replace(/\s+/g,' ').trim();
function day(value){if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;const millis=Date.parse(value);return Number.isFinite(millis)?new Date(millis+9*3600000).toISOString().slice(0,10):''}
function shuffle(rows,rng=Math.random){const a=[...rows];for(let i=a.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
function balanced(rows){const buckets=new Map();for(const a of rows){if(!buckets.has(a.author_id))buckets.set(a.author_id,[]);buckets.get(a.author_id).push(a)}let active=[...buckets.values()];const out=[];let index=0;while(active.length){const next=[];for(const a of active){out.push(a[index]);if(a.length>index+1)next.push(a)}active=next;index++}return out}
function filter(rows,f,groups=[]){const terms=norm(f.q).split(' ').filter(Boolean);const exact=groups.filter(g=>[g.name,...(g.aliases||[])].some(alias=>norm(alias)===norm(f.q))).map(g=>g.id);return rows.filter(a=>(!exact.length||a.group_ids.some(id=>exact.includes(id)))&&terms.every(t=>a.search.includes(t))&&(!f.category||a.category_ids.includes(f.category))&&(!f.group||a.group_ids.includes(f.group))&&(!f.topic||a.topic_ids.includes(f.topic))&&(!f.era||Math.floor(Number(day(a.published_at).slice(0,4))/10)*10===Number(f.era))&&(!f.author||a.author_id===f.author))}
function draw(rows,rng=Math.random){const ids=[...new Set(rows.map(a=>a.author_id))];if(!ids.length)return null;const id=ids[Math.floor(rng()*ids.length)];const own=rows.filter(a=>a.author_id===id);return own[Math.floor(rng()*own.length)]}
const api={norm,day,shuffle,balanced,filter,draw};root.AntennaCore=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
