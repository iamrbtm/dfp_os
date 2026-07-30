(function () {
  "use strict";

  var hero = document.querySelector('[data-hero-asymmetry]');
  if (!hero || !window.gsap) return;

  var mm = window.gsap.matchMedia();

  mm.add(
    {
      animate: '(prefers-reduced-motion: no-preference)',
      compact: '(max-width: 650px)',
      tablet: '(max-width: 1020px)',
    },
    function (context) {
      if (!context.conditions.animate) return;

      var compact = context.conditions.compact;
      var tablet = context.conditions.tablet;
      var isMobile = compact || tablet;

      /* ===========================
         1. Glass Nav Entrance
         =========================== */
      var nav = document.querySelector('.glass-nav');
      if (nav) {
        window.gsap.from(nav, {
          y: -30,
          opacity: 0,
          duration: 0.6,
          ease: 'power3.out',
          clearProps: 'opacity,transform',
        });

        /* Nav scrolled state */
        var navToggle = function () {
          if (window.scrollY > 80) {
            nav.classList.add('glass-nav--scrolled');
          } else {
            nav.classList.remove('glass-nav--scrolled');
          }
        };
        window.addEventListener('scroll', navToggle, { passive: true });
      }

      /* ===========================
         2. Hero Artistic Asymmetry
         =========================== */
      var copy = hero.querySelector('.hero-asymmetry__copy');
      var art = hero.querySelector('.hero-asymmetry__art');
      var floatEl = hero.querySelector('.hero-asymmetry__float');

      /* Text elements stagger in from left */
      window.gsap.from(
        copy.querySelectorAll(
          '.hero-asymmetry__kicker, .hero-asymmetry__title, .hero-asymmetry__lede, .hero-asymmetry__actions, .hero-asymmetry__trust'
        ),
        {
          x: -50,
          autoAlpha: 0,
          stagger: 0.1,
          duration: 0.7,
          ease: 'power3.out',
          clearProps: 'opacity,visibility,transform',
        }
      );

      /* Art element floats in from bottom-right */
      window.gsap.from(art, {
        x: isMobile ? 30 : 60,
        y: isMobile ? 40 : 60,
        autoAlpha: 0,
        duration: 0.9,
        delay: 0.15,
        ease: 'power3.out',
        clearProps: 'opacity,visibility,transform',
      });

      /* Floating rings subtle idle animation */
      var rings = art.querySelectorAll('.hero-asymmetry__float-ring');
      if (rings.length) {
        window.gsap.to(rings, {
          rotation: '+=6',
          duration: 4,
          ease: 'sine.inOut',
          yoyo: true,
          repeat: -1,
        });
      }

      /* Float shape subtle bob */
      var shape = art.querySelector('.hero-asymmetry__float-shape');
      if (shape) {
        window.gsap.to(shape, {
          y: -8,
          duration: 3.5,
          ease: 'sine.inOut',
          yoyo: true,
          repeat: -1,
          delay: 0.5,
        });
      }

      /* Float chips stagger in */
      window.gsap.from(art.querySelectorAll('.hero-asymmetry__float-chip'), {
        scale: 0,
        autoAlpha: 0,
        duration: 0.5,
        delay: 0.6,
        stagger: 0.12,
        ease: 'back.out(2)',
        clearProps: 'opacity,visibility,transform',
      });

      /* ===========================
         3. Bento Grid (Product Lanes)
         =========================== */
      var bentoSection = document.querySelector('[data-bento-reveal]');
      if (bentoSection) {
        var bentoObserver = new IntersectionObserver(
          function (entries, observer) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              var cards = entry.target.querySelectorAll('.bento-card');
              window.gsap.from(cards, {
                y: 40,
                scale: 0.95,
                autoAlpha: 0,
                stagger: 0.08,
                duration: 0.6,
                ease: 'power3.out',
                clearProps: 'opacity,visibility,transform',
              });
              observer.unobserve(entry.target);
            });
          },
          { rootMargin: '0px 0px -10% 0px', threshold: 0.1 }
        );
        bentoObserver.observe(bentoSection);
      }

      /* ===========================
         4. Product Grid (Image Scale & Fade Scroll)
         =========================== */
      var productCards = document.querySelectorAll('.product-card-cinematic');
      if (productCards.length) {
        /* Entrance stagger */
        window.gsap.from(productCards, {
          y: 30,
          autoAlpha: 0,
          stagger: 0.06,
          duration: 0.55,
          ease: 'power2.out',
          clearProps: 'opacity,visibility,transform',
          scrollTrigger: {
            trigger: productCards[0].closest('[data-products-reveal]') || productCards[0].parentElement,
            start: 'top 80%',
            toggleActions: 'play none none reverse',
          },
        });

        /* Image Scale & Fade Scroll */
        if (!isMobile) {
          productCards.forEach(function (card) {
            var img = card.querySelector('.product-card-cinematic__image');
            if (!img) return;
            window.gsap.from(img, {
              scale: 0.82,
              duration: 1.2,
              ease: 'power2.out',
              scrollTrigger: {
                trigger: card,
                start: 'top 85%',
                end: 'top 40%',
                scrub: 1.2,
              },
            });
            window.gsap.to(img, {
              opacity: 0.3,
              scale: 0.92,
              duration: 1,
              ease: 'power2.in',
              scrollTrigger: {
                trigger: card,
                start: 'bottom 20%',
                end: 'bottom -30%',
                scrub: 1,
              },
            });
          });
        }
      }

      /* ===========================
         5. Split Screen (Custom Order)
         =========================== */
      var splitSection = document.querySelector('[data-split-reveal]');
      if (splitSection) {
        var splitObserver = new IntersectionObserver(
          function (entries, obs) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;

              /* Text side reveals */
              var textSide = entry.target.querySelector('.split-screen__text');
              if (textSide) {
                window.gsap.from(textSide.querySelectorAll('*'), {
                  y: 20,
                  autoAlpha: 0,
                  stagger: 0.06,
                  duration: 0.5,
                  ease: 'power2.out',
                  clearProps: 'opacity,visibility,transform',
                });
              }

              /* Counter number animation */
              var counterItems = entry.target.querySelectorAll('.split-screen__counter-number');
              counterItems.forEach(function (el) {
                var target = parseInt(el.getAttribute('data-count'), 10) || 0;
                if (target === 0) return;
                var obj = { val: 0 };
                window.gsap.to(obj, {
                  val: target,
                  duration: 2,
                  ease: 'power2.out',
                  onUpdate: function () {
                    el.textContent = Math.round(obj.val);
                  },
                });
              });

              /* Timeline strip items stagger */
              var timelineItems = entry.target.querySelectorAll('.timeline-strip__item');
              window.gsap.from(timelineItems, {
                x: 40,
                autoAlpha: 0,
                stagger: 0.1,
                duration: 0.5,
                ease: 'power3.out',
                clearProps: 'opacity,visibility,transform',
              });

              obs.unobserve(entry.target);
            });
          },
          { rootMargin: '0px 0px -8% 0px', threshold: 0.1 }
        );
        splitObserver.observe(splitSection);
      }

      /* ===========================
         6. Section Reveal Observer (General)
         =========================== */
      var revealSections = document.querySelectorAll('[data-reveal]');
      if (revealSections.length) {
        var revealObserver = new IntersectionObserver(
          function (entries, obs) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              window.gsap.from(entry.target, {
                y: 30,
                autoAlpha: 0,
                duration: 0.6,
                ease: 'power2.out',
                clearProps: 'opacity,visibility,transform',
              });
              obs.unobserve(entry.target);
            });
          },
          { rootMargin: '0px 0px -10% 0px', threshold: 0.08 }
        );
        revealSections.forEach(function (el) {
          revealObserver.observe(el);
        });
      }

      /* ===========================
         7. Cleanup
         =========================== */
      return function () {
        if (nav) nav.classList.remove('glass-nav--scrolled');
      };
    }
  );
})();
