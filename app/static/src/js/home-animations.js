(() => {
  const hero = document.querySelector("[data-home-hero]");

  if (!hero || !window.gsap) {
    return;
  }

  const mm = window.gsap.matchMedia();

  mm.add(
    {
      animate: "(prefers-reduced-motion: no-preference)",
      compact: "(max-width: 650px)",
    },
    (context) => {
      if (!context.conditions.animate) {
        return;
      }

      const { compact } = context.conditions;
      const heroCopy = hero.querySelector(".public-hero__copy");
      const stage = hero.querySelector(".filament-stage");

      window.gsap.from(
        [
          heroCopy.querySelector(".public-kicker"),
          heroCopy.querySelector("h1"),
          heroCopy.querySelector(".public-hero__lede"),
          heroCopy.querySelector(".public-actions"),
          heroCopy.querySelector(".public-trust"),
        ],
        {
          autoAlpha: 0,
          y: compact ? 18 : 26,
          stagger: 0.09,
          duration: compact ? 0.55 : 0.7,
          ease: "power2.out",
          clearProps: "opacity,visibility,transform",
        },
      );

      window.gsap.from(stage, {
        autoAlpha: 0,
        scale: compact ? 0.94 : 0.9,
        rotation: compact ? 0 : -3,
        duration: compact ? 0.65 : 0.9,
        delay: 0.12,
        ease: "back.out(1.25)",
        clearProps: "opacity,visibility,transform",
      });

      window.gsap.from(stage.querySelectorAll(".color-chip"), {
        autoAlpha: 0,
        scale: 0.7,
        y: 12,
        duration: 0.45,
        delay: 0.48,
        stagger: 0.1,
        ease: "back.out(1.7)",
        clearProps: "opacity,visibility,transform",
      });

      const revealObserver = new IntersectionObserver(
        (entries, observer) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) {
              return;
            }

            const section = entry.target;
            const heading = section.querySelector(".section-heading");
            const items = section.querySelectorAll(
              ".lane-card, .public-product-card, .custom-story li, .market-card, .learn-strip > div",
            );

            if (heading) {
              window.gsap.from(heading, {
                autoAlpha: 0,
                y: 20,
                duration: 0.55,
                ease: "power2.out",
                clearProps: "opacity,visibility,transform",
              });
            }

            if (items.length) {
              window.gsap.from(items, {
                autoAlpha: 0,
                y: compact ? 14 : 24,
                stagger: 0.08,
                duration: 0.5,
                delay: heading ? 0.08 : 0,
                ease: "power2.out",
                clearProps: "opacity,visibility,transform",
              });
            }

            observer.unobserve(section);
          });
        },
        { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
      );

      document.querySelectorAll("[data-reveal-section]").forEach((section) => {
        revealObserver.observe(section);
      });

      return () => revealObserver.disconnect();
    },
  );
})();
