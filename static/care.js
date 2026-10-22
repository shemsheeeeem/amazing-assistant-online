(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.querySelectorAll("[data-carousel]").forEach((carousel) => {
    const slides = Array.from(carousel.querySelectorAll(".cr-review"));
    const dots = Array.from(carousel.querySelectorAll("[data-go]"));
    const count = slides.length;
    if (count < 2) return;

    let current = 0;
    let timer = null;

    const show = (index) => {
      current = (index + count) % count;
      slides.forEach((slide, i) => {
        let pos = i - current;
        if (pos > count / 2) pos -= count;
        if (pos < -count / 2) pos += count;
        slide.dataset.pos = Math.max(-2, Math.min(2, pos));
        slide.setAttribute("aria-hidden", pos === 0 ? "false" : "true");
        slide.querySelectorAll("a").forEach((link) => { link.tabIndex = pos === 0 ? 0 : -1; });
      });
      dots.forEach((dot, i) => dot.toggleAttribute("aria-current", i === current));
    };

    const stop = () => { clearInterval(timer); timer = null; };
    const start = () => {
      if (reduceMotion || timer) return;
      timer = setInterval(() => show(current + 1), 5500);
    };

    carousel.addEventListener("click", (event) => {
      const step = event.target.closest("[data-step]");
      const dot = event.target.closest("[data-go]");
      const side = event.target.closest(".cr-review:not([data-pos='0'])");
      if (step) show(current + Number(step.dataset.step));
      else if (dot) show(Number(dot.dataset.go));
      else if (side) { event.preventDefault(); show(slides.indexOf(side)); }
      else return;
      stop();
      start();
    });

    carousel.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") show(current - 1);
      else if (event.key === "ArrowRight") show(current + 1);
    });

    let touchX = null;
    carousel.addEventListener("touchstart", (event) => { touchX = event.touches[0].clientX; }, { passive: true });
    carousel.addEventListener("touchend", (event) => {
      if (touchX === null) return;
      const dx = event.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) show(current + (dx < 0 ? 1 : -1));
      touchX = null;
    });

    carousel.addEventListener("mouseenter", stop);
    carousel.addEventListener("mouseleave", start);
    carousel.addEventListener("focusin", stop);
    carousel.addEventListener("focusout", start);

    show(0);
    start();
  });
})();
