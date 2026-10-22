(function () {
  if (!window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);

  const mm = gsap.matchMedia();

  mm.add("(prefers-reduced-motion: no-preference)", () => {
    let lenis = null;
    const raf = (time) => lenis.raf(time * 1000);
    if (window.Lenis) {
      lenis = new Lenis({ duration: 1.15, anchors: true, smoothWheel: true });
      lenis.on("scroll", ScrollTrigger.update);
      gsap.ticker.add(raf);
      gsap.ticker.lagSmoothing(0);
    }

    const bar = document.createElement("div");
    bar.className = "scroll-progress";
    bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
    gsap.to(bar, {
      scaleX: 1,
      ease: "none",
      scrollTrigger: { start: 0, end: "max", scrub: 0.3 },
    });

    ScrollTrigger.create({
      start: 12,
      end: "max",
      toggleClass: { targets: document.body, className: "is-scrolled" },
    });

    const revealGroups = [
      ".band-dark h3, .section-intro, .lp-intro, .page-head, .section-head",
      ".job-card, .person-tile, .features article, .chip, .stats > div",
      ".review-card",
      ".cat-heading, .cat-tile",
      ".plan",
      ".lp-card, .lp-tool, .lp-faq details, .lp-band-copy > *, .lp-form-mock",
      ".cta-inner > *, .lp-cta-inner > :not(svg)",
      ".panel, .hero-ticket, .person-card, .app-card, .dash-row, .filters, .role, .demo",
      ".cr-kicker, .cr-section h2, .cr-intro, .cr-trust li",
      ".cr-card, .cr-team li",
      ".cr-timeline li, .cr-faq details",
      ".cr-banner, .cr-quote blockquote",
      ".foot > *",
    ];

    revealGroups.forEach((selector) => {
      const items = gsap.utils.toArray(selector);
      if (!items.length) return;
      gsap.set(items, { autoAlpha: 0, y: 36 });
      items.forEach((el) => el.classList.add("motion-busy"));
      ScrollTrigger.batch(items, {
        start: "top 90%",
        once: true,
        onEnter: (batch) =>
          gsap.to(batch, {
            autoAlpha: 1,
            y: 0,
            duration: 0.8,
            ease: "power3.out",
            stagger: 0.08,
            overwrite: true,
            onComplete() {
              batch.forEach((el) => el.classList.remove("motion-busy"));
              gsap.set(batch, { clearProps: "transform,opacity,visibility" });
            },
          }),
      });
    });

    gsap.utils.toArray(".stats strong, .cr-banner h2 span").forEach((el) => {
      const target = parseInt(el.textContent, 10);
      if (!Number.isFinite(target)) return;
      const counter = { value: 0 };
      el.textContent = "0";
      gsap.to(counter, {
        value: target,
        duration: 1.6,
        ease: "power2.out",
        scrollTrigger: { trigger: el, start: "top 90%", once: true },
        onUpdate: () => { el.textContent = Math.round(counter.value); },
      });
    });

    const steps = gsap.utils.toArray(".lp-steps li");
    if (steps.length) {
      gsap.from(steps, {
        scale: 0,
        duration: 0.6,
        ease: "back.out(2)",
        stagger: 0.18,
        scrollTrigger: { trigger: ".lp-steps", start: "top 85%", once: true },
      });
    }

    const notes = gsap.utils.toArray(".window .note");
    if (notes.length) {
      gsap.from(notes, { autoAlpha: 0, x: 24, duration: 0.6, ease: "power3.out", stagger: 0.09, delay: 0.45 });
    }

    const art = document.querySelector(".art-bg");
    if (art) {
      gsap.to(art, {
        y: 60,
        ease: "none",
        scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true },
      });
    }

    gsap.utils.toArray(".lp-hero .lp-doodle").forEach((el, i) => {
      gsap.to(el, {
        y: -(80 + i * 40),
        ease: "none",
        scrollTrigger: { trigger: ".lp-hero", start: "top top", end: "bottom top", scrub: true },
      });
    });

    const app = document.querySelector(".lp-app");
    if (app) {
      gsap.fromTo(
        app,
        { rotationX: 16, y: 40, scale: 0.94, transformPerspective: 1400, transformOrigin: "50% 0%" },
        {
          rotationX: 0,
          y: 0,
          scale: 1,
          ease: "none",
          scrollTrigger: { trigger: app, start: "top bottom", end: "top 25%", scrub: 0.6 },
        }
      );
    }

    document.fonts && document.fonts.ready.then(() => ScrollTrigger.refresh());

    return () => {
      if (lenis) {
        gsap.ticker.remove(raf);
        lenis.destroy();
      }
      bar.remove();
    };
  });
})();
