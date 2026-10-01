'use strict';
// This local preference can reduce motion further; OS reduction always wins in CSS.
(() => {
  const root = document.documentElement;
  const checkbox = document.getElementById('reduce-motion');
  if (!checkbox) return;
  let reduced = false;
  try { reduced = localStorage.getItem('dots-panel-reduced-motion') === 'true'; } catch (_) {}
  const apply = () => { root.dataset.reducedMotion = String(reduced); checkbox.checked = reduced; };
  const labels = () => {
    const en = root.lang.startsWith('en');
    document.getElementById('motion-label').textContent = en ? 'Reduce motion' : '减少动效';
    document.getElementById('motion-description').textContent = en ? 'Short interaction feedback only. Your system’s reduced-motion preference is always respected.' : '仅在交互时提供短暂反馈；始终遵循系统的减少动态效果偏好。';
  };
  checkbox.addEventListener('change', () => {
    reduced = checkbox.checked;
    apply();
    try { localStorage.setItem('dots-panel-reduced-motion', String(reduced)); }
    catch (_) { document.getElementById('motion-description').textContent = root.lang.startsWith('en') ? 'Applied for this visit; preference could not be saved.' : '本次访问已生效；偏好未能保存。'; }
  });
  apply(); labels();
  new MutationObserver(labels).observe(root, {attributes:true, attributeFilter:['lang']});
})();
