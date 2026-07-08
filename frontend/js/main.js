// Landing page asosiy skripti
import { initErrorHandler } from './core/error-handler.js';
initErrorHandler();

// ── Theme ──────────────────────────────────────────────────────────────────────
const themeToggle = document.getElementById('themeToggle');
const html        = document.documentElement;
const stored      = localStorage.getItem('theme') || 'dark';

function setTheme(t) {
    html.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    const sunIcon  = themeToggle?.querySelector('.sun-icon');
    const moonIcon = themeToggle?.querySelector('.moon-icon');
    if (sunIcon)  sunIcon.style.display  = t === 'dark'  ? 'block' : 'none';
    if (moonIcon) moonIcon.style.display = t === 'light' ? 'block' : 'none';
}

setTheme(stored);
themeToggle?.addEventListener('click', () => {
    setTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

// ── Mobile menu ────────────────────────────────────────────────────────────────
const menuToggle = document.querySelector('.mobile-menu-toggle');
const navMenu    = document.querySelector('.navbar-menu');

menuToggle?.addEventListener('click', () => {
    navMenu?.classList.toggle('open');
});

// Close menu on link click
navMenu?.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => navMenu.classList.remove('open'));
});

// ── Smooth scroll for anchor links ─────────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
        const id  = a.getAttribute('href').slice(1);
        const el  = document.getElementById(id);
        if (el) { e.preventDefault(); el.scrollIntoView({ behavior: 'smooth' }); }
    });
});

// ── Intersection Observer: fade-in animatsiya ──────────────────────────────────
const observer = new IntersectionObserver(
    entries => entries.forEach(en => {
        if (en.isIntersecting) {
            en.target.style.opacity  = '1';
            en.target.style.transform = 'translateY(0)';
        }
    }),
    { threshold: 0.1 }
);

document.querySelectorAll('.feature-card, .access-card, .stat-item').forEach(el => {
    el.style.opacity   = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    observer.observe(el);
});

// ── Navbar scroll effect ────────────────────────────────────────────────────────
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
    navbar?.classList.toggle('scrolled', window.scrollY > 50);
});

// ── Service Worker ro'yxatdan o'tkazish ──────────────────────────────────────────
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('pwa/service-worker.js')
        .catch(() => {});
}
