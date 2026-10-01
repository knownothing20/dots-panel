'use strict';
// Small DOM adapter for existing synthetic browser fixtures (no dependencies).
module.exports=(Node,getDocument)=>{
 Object.defineProperties(Node.prototype,{
  nodeType:{get(){return this.tag==='#text'?3:1;}},nodeName:{get(){return String(this.tag||'div').toUpperCase();}},
  childNodes:{get(){return this.children;}},parentNode:{get(){return this.parentElement;}},
  nextSibling:{get(){const siblings=this.parentElement?.children||[];return siblings[siblings.indexOf(this)+1]||null;}},
  ownerDocument:{get(){return getDocument();}},attributes:{get(){return Object.entries(this.attrs||{}).map(([name,value])=>({name,value:String(value)}));}},
 });
 Node.prototype.removeEventListener=function(type,callback){if(this.listeners[type]===callback)delete this.listeners[type];};
 Node.prototype.hasAttribute=function(k){return this.getAttribute(k)!=null;};
 Node.prototype.insertBefore=function(node,before){if(node.parentElement){const old=node.parentElement.children;const i=old.indexOf(node);if(i>=0)old.splice(i,1);}const index=before?this.children.indexOf(before):-1;this.children.splice(index<0?this.children.length:index,0,node);node.parentElement=this;return node;};
 Node.prototype.remove=function(){if(this.parentElement){const i=this.parentElement.children.indexOf(this);if(i>=0)this.parentElement.children.splice(i,1);this.parentElement=null;}};
 Node.prototype.cloneNode=function(deep=false){const n=new Node(this.tag);n.id=this.id;n.className=this.className;n.attrs={...this.attrs};n.dataset={...this.dataset};n.hidden=this.hidden;n.disabled=this.disabled;n.open=this.open;n.value=this.value;n.textContent=this.textContent;if(deep)for(const c of this.children)n.append(c.cloneNode(true));return n;};
};
