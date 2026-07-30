/**
 * PharmacyPro Landing Page — Vanilla JavaScript
 * Handles smooth scrolling for nav anchors and checkout button analytics.
 */

(function () {
    'use strict';

    // ── Smooth Scroll for Navigation Links ────────────────────────────
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener('click', function (e) {
            var targetId = this.getAttribute('href');
            if (targetId === '#') return;

            var target = document.querySelector(targetId);
            if (!target) return;

            e.preventDefault();
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            });

            // Update URL hash without jumping
            history.pushState(null, '', targetId);
        });
    });

    // ── Checkout Button Analytics Placeholder ─────────────────────────
    var checkoutBtns = document.querySelectorAll('#checkout-btn, #pricing-checkout-btn');
    checkoutBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            console.log('[PharmacyPro] Checkout CTA clicked:', this.href);
            // TODO: Wire up to analytics (Plausible, Umami, or GA4)
            // Example: window.plausible && window.plausible('Checkout Click');
        });
    });

    // ── Navbar Background on Scroll ───────────────────────────────────
    var navbar = document.getElementById('navbar');
    if (navbar) {
        var scrollThreshold = 50;
        window.addEventListener('scroll', function () {
            if (window.scrollY > scrollThreshold) {
                navbar.style.background = 'rgba(15, 23, 42, .95)';
            } else {
                navbar.style.background = 'rgba(15, 23, 42, .85)';
            }
        });
    }

    // ── Intersection Observer for Fade-In Animations ──────────────────
    if ('IntersectionObserver' in window) {
        var fadeElements = document.querySelectorAll(
            '.feature-card, .step, .pricing-card'
        );

        fadeElements.forEach(function (el) {
            el.style.opacity = '0';
            el.style.transform = 'translateY(24px)';
            el.style.transition = 'opacity .6s ease, transform .6s ease';
        });

        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
        );

        fadeElements.forEach(function (el) {
            observer.observe(el);
        });
    }
})();
