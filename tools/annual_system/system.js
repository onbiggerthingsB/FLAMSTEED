/* ============================================================
   THE ANNUAL — shared behaviour for flamsteed.io
   Canonical source: tools/annual_system/system.js
   Spec §4: docs/superpowers/specs/2026-08-12-site-redesign-annual-design.md

   Two blocks, copied verbatim into every page inside its own pair
   of script tags. Nothing is fetched, nothing is generated, no
   state is stored. Together they are the whole behaviour of the
   site. (Neither block may ever contain the literal closing tag
   of a script element — it would end the element early.)

   BLOCK A goes in <head>, BEFORE <style>, so the first paint is
   already on the correct path.
   BLOCK B goes at the end of <body>.

   THE TWO-PATH RULE. Block A adds `.js` only when motion is
   welcome AND observable. Every animated style in system.css
   lives under `.js`. So the document without these two scripts is
   the finished document, and no-JS, reduced-motion and
   old-browser are the same single path — provably, not by
   assertion. The DOM ships final values; nothing here writes
   copy, numbers, or markup.

   Overprint contract (spec §4): a plate with a realized layer is
   <figure class="plate has-overprint">, its realized layer is
   .overprint-layer, its marginal delta is .op-delta, and its
   control is <button class="op-btn" aria-pressed="false">. Both
   layers ship drawn; only `.js` hides the realized one until the
   reader asks for it.
   ============================================================ */

/* ===== BLOCK A — <head>, before <style> ===================== */
(function () {
  try {
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches &&
        'IntersectionObserver' in window) {
      document.documentElement.classList.add('js');
    }
  } catch (e) {}
})();

/* ===== BLOCK B — end of <body> ============================== */
(function () {
  if (!document.documentElement.classList.contains('js')) return;

  // Reveal on approach: plates draw, rules extend, footnotes fade.
  // One-shot — nothing re-animates on the way back up.
  //
  // SCREENSHOT CAVEAT. The footnote strip is the one element that starts
  // at opacity 0 under .js, so a full-page screenshot taken without
  // scrolling photographs it blank. When capturing proof screenshots of
  // a JS-enabled page, scroll to the foot first (or capture the
  // script-free page, which never hides anything). Print is already
  // handled: the print block in system.css forces the end state.
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    });
  }, { threshold: .25, rootMargin: '0px 0px -8% 0px' });
  document.querySelectorAll('.plate,.watch').forEach(function (el) { io.observe(el); });

  // The errata overprint. The label never changes; aria-pressed
  // carries the state, which is what a toggle button owes a
  // screen reader.
  document.querySelectorAll('.op-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      var p = b.closest('.plate');
      if (!p) return;
      p.classList.toggle('printed');
      b.setAttribute('aria-pressed', p.classList.contains('printed'));
    });
  });
})();
