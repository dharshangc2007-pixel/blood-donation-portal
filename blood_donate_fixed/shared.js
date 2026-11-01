/* ============================================
   shared.js – Common JS for all pages
   LifeFlow Blood Donation Camp
   ============================================ */

// ============================================
// SCROLL PROGRESS BAR
// ============================================
window.addEventListener('scroll', () => {
  const scrollTop    = document.documentElement.scrollTop || document.body.scrollTop;
  const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
  const progress     = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
  const bar          = document.getElementById('progressBar');
  if (bar) bar.style.width = progress + '%';
});

// ============================================
// FLOATING PARTICLES
// ============================================
(function createParticles() {
  const container = document.getElementById('particles');
  if (!container) return;
  const colors = [
    'rgba(220,20,60,0.35)',
    'rgba(255,107,138,0.22)',
    'rgba(139,0,0,0.28)'
  ];
  for (let i = 0; i < 18; i++) {
    const p = document.createElement('div');
    p.classList.add('particle');
    p.style.left              = Math.random() * 100 + '%';
    p.style.animationDuration = (8 + Math.random() * 12) + 's';
    p.style.animationDelay   = (Math.random() * 10) + 's';
    p.style.background        = colors[Math.floor(Math.random() * colors.length)];
    const size = (2 + Math.random() * 4) + 'px';
    p.style.width  = size;
    p.style.height = size;
    container.appendChild(p);
  }
})();

// ============================================
// NAVBAR — shrink on scroll
// ============================================
window.addEventListener('scroll', () => {
  const navbar = document.getElementById('mainNavbar');
  if (!navbar) return;
  if (window.scrollY > 60) {
    navbar.style.padding    = '10px 40px';
    navbar.style.background = 'rgba(10,10,15,0.97)';
  } else {
    navbar.style.padding    = '16px 40px';
    navbar.style.background = 'rgba(10,10,15,0.8)';
  }
});

// ============================================
// HAMBURGER MENU — mobile toggle
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  const hamburger = document.getElementById('hamburgerBtn');
  const navLinks  = document.getElementById('navLinks');
  if (!hamburger || !navLinks) return;

  hamburger.addEventListener('click', () => {
    const isOpen = navLinks.classList.contains('mobile-open');
    if (isOpen) {
      navLinks.classList.remove('mobile-open');
      navLinks.removeAttribute('style');
    } else {
      navLinks.classList.add('mobile-open');
      Object.assign(navLinks.style, {
        display        : 'flex',
        flexDirection  : 'column',
        position       : 'absolute',
        top            : '66px',
        left           : '0',
        right          : '0',
        background     : 'rgba(10,10,15,0.98)',
        padding        : '20px 24px',
        borderBottom   : '1px solid rgba(220,20,60,0.2)',
        backdropFilter : 'blur(20px)',
        gap            : '18px',
        zIndex         : '999'
      });
    }
  });

  // Close menu when a link is clicked
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      navLinks.classList.remove('mobile-open');
      navLinks.removeAttribute('style');
    });
  });
});

// ============================================
// SMOOTH SCROLL — anchor links
// ============================================
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      const offset = 90;
      const top    = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  });
});

// ============================================
// INTERSECTION OBSERVER — fade-in on scroll
// ============================================
const fadeObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity   = '1';
      entry.target.style.transform = 'translateY(0)';
      fadeObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.08 });

document.querySelectorAll(
  '.info-card, .schedule-card, .testimonial-card, .faq-item, ' +
  '.team-card, .value-card, .strip-item, .contact-info-item, .schedule-list-item'
).forEach(el => {
  el.style.opacity   = '0';
  el.style.transform = 'translateY(22px)';
  el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  fadeObserver.observe(el);
});

// ============================================
// ACTIVE NAV LINK HIGHLIGHT
// ============================================
(function highlightNav() {
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPage) {
      link.style.color = '#ff4d6d';
    }
  });
})();
