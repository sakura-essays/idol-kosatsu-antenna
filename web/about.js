'use strict';
(()=>{
  const toc=document.getElementById('policy-toc');
  const desktop=matchMedia('(min-width:861px)');
  const sync=()=>{toc.open=desktop.matches;};
  sync();
  desktop.addEventListener('change',sync);
})();
