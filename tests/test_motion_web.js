'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/motion.js','utf8');
function fixture(saved, failure=false){
  const root={lang:'en',dataset:{}};
  const nodes={'reduce-motion':{checked:false,addEventListener(type,fn){this[type]=fn;}},'motion-label':{},'motion-description':{}};
  const writes=[];let observer;
  vm.runInNewContext(source,{document:{documentElement:root,getElementById:id=>nodes[id]},localStorage:{getItem:()=>saved,setItem:(k,v)=>{if(failure)throw Error('blocked');writes.push([k,v]);}},MutationObserver:class{constructor(fn){observer=fn;}observe(){}}});
  return {root,nodes,writes,observer};
}
{
  const f=fixture('true');assert.equal(f.root.dataset.reducedMotion,'true');assert.equal(f.nodes['reduce-motion'].checked,true);
  f.nodes['reduce-motion'].checked=false;f.nodes['reduce-motion'].change();assert.equal(f.root.dataset.reducedMotion,'false');assert.deepEqual(f.writes,[['dots-panel-reduced-motion','false']]);
  f.root.lang='zh-CN';f.observer();assert.equal(f.nodes['motion-label'].textContent,'减少动效');
}
{
  const f=fixture(null,true);f.nodes['reduce-motion'].checked=true;f.nodes['reduce-motion'].change();assert.equal(f.root.dataset.reducedMotion,'true');assert.match(f.nodes['motion-description'].textContent,/could not be saved/);
}
const css=fs.readFileSync('web/motion.css','utf8');
assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
assert.match(css,/animation:none!important;transition:none!important/);
assert.match(css,/--motion-fast:160ms/);
assert.doesNotMatch(css,/@keyframes/); // No repeating decorative animation.
console.log('Motion preferences, language, storage failure, and reduced-motion CSS checks passed');
