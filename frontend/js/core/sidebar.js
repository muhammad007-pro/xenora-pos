/**
 * Dinamik sidebar (BOSQICH 4.2)
 *
 * Feature flags asosida sidebar nav-item larini ko'rsatadi/yashiradi.
 * HTML da: <a class="nav-item" data-feature="kitchen_display" href="kitchen.html">
 * Bu atribut yo'q bo'lsa — doimo ko'rinadi.
 *
 * Ishlatilishi:
 *   import { Sidebar } from './sidebar.js';
 *   await Sidebar.init();
 */

import { features, Feature, BUSINESS_LABELS } from './features.js';
import { AuthService } from './auth.js';

// Har bir biznes turi uchun sidebar menyusi konfiguratsiyasi
// `feature` yo'q bo'lsa → har doim ko'rinadi
// `roles` yo'q bo'lsa → barcha rollar ko'ra oladi
const NAV_CONFIG = [
    {
        id:      'nav-pos',
        label:   'POS Terminal',
        href:    '/app/pos.html',
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="2" width="20" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="8" cy="8" r="2" fill="currentColor"/>
                    <circle cx="16" cy="8" r="2" fill="currentColor"/>
                    <circle cx="8" cy="16" r="2" fill="currentColor"/>
                    <circle cx="16" cy="16" r="2" fill="currentColor"/>
                  </svg>`,
    },
    {
        id:      'nav-kitchen',
        label:   'Oshxona',
        href:    '/app/kitchen.html',
        feature: Feature.KITCHEN_DISPLAY,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M4 8h16v12a2 2 0 01-2 2H6a2 2 0 01-2-2V8z" stroke="currentColor" stroke-width="2"/>
                    <path d="M8 4V2h8v2" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-tables',
        label:   'Stollar',
        href:    '/app/tables.html',
        feature: Feature.TABLE_MANAGEMENT,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="7" width="20" height="10" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M6 17v3M18 17v3M6 7V4M18 7V4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-reservations',
        label:   'Bronlar',
        href:    '/app/reservations.html',
        feature: Feature.TABLE_RESERVATION,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M3 10h18M8 2v4M16 2v4" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-appointments',
        label:   'Uchrashuvlar',
        href:    '/app/appointments.html',
        feature: Feature.TIME_BOOKING,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-services',
        label:   'Xizmatlar',
        href:    '/app/services.html',
        feature: Feature.SERVICES,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-customers',
        label:   'Mijozlar',
        href:    '/app/customers.html',
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="2"/>
                    <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-inventory',
        label:   'Ombor',
        href:    '/app/inventory.html',
        feature: Feature.INVENTORY,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="7" width="20" height="14" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-recipes',
        label:   'Retseptlar',
        href:    '/app/recipes.html',
        feature: Feature.RECIPE,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" stroke="currentColor" stroke-width="2"/>
                    <rect x="9" y="3" width="6" height="4" rx="1" stroke="currentColor" stroke-width="2"/>
                    <path d="M9 12h6M9 16h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-loyalty',
        label:   'Sodiqlik dasturi',
        href:    '/app/loyalty.html',
        feature: Feature.LOYALTY,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-barcode',
        label:   'Barcode skaner',
        href:    '/app/barcode.html',
        feature: Feature.BARCODE,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M2 4h2v16H2V4zM5 4h1v16H5V4zM7 4h3v16H7V4zM11 4h1v16h-1V4zM13 4h2v16h-2V4zM16 4h1v16h-1V4zM18 4h4v16h-4V4z" fill="currentColor"/>
                  </svg>`,
    },
    {
        id:      'nav-expiry',
        label:   'Muddat nazorati',
        href:    '/app/expiry.html',
        feature: Feature.EXPIRY_DATE,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-prescriptions',
        label:   'Retsept arxivi',
        href:    '/app/prescriptions.html',
        feature: Feature.PRESCRIPTION_ARCHIVE,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" stroke-width="2"/>
                    <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-batches',
        label:   'Partiya nazorati',
        href:    '/app/batches.html',
        feature: Feature.BATCH_TRACKING,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" stroke="currentColor" stroke-width="2"/>
                    <path d="M3.27 6.96L12 12.01l8.73-5.05M12 22.08V12" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    // ── BOSQICH 23: Salon nav elementlari ──────────────────────────────────
    {
        id:      'nav-staff-schedule',
        label:   'Usta jadvali',
        href:    '/app/salon_schedule.html',
        feature: Feature.STAFF_SCHEDULE,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M16 2v4M8 2v4M3 10h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-client-photos',
        label:   'Oldin / Keyin',
        href:    '/app/client_photos.html',
        feature: Feature.BEFORE_AFTER_PHOTO,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
                    <path d="M21 15l-5-5L5 21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 3v18" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2"/>
                  </svg>`,
    },
    {
        id:      'nav-salon-analytics',
        label:   'Salon tahlili',
        href:    '/app/salon_analytics.html',
        feature: Feature.COMMISSION_REPORT,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-suppliers',
        label:   'Yetkazib beruvchilar',
        href:    '/app/suppliers.html',
        feature: Feature.SUPPLIER_CARD,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M1 3h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 001.95-1.57l1.65-7.43H5.12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="10" cy="20.5" r="1" stroke="currentColor" stroke-width="2"/>
                    <circle cx="17.5" cy="20.5" r="1" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-purchase-receipts',
        label:   'Priyomka',
        href:    '/app/purchase_receipts.html',
        feature: Feature.PURCHASE_RECEIPT,
        roles:   ['admin', 'manager', 'storekeeper'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" stroke="currentColor" stroke-width="2"/>
                    <rect x="9" y="3" width="6" height="4" rx="1" stroke="currentColor" stroke-width="2"/>
                    <path d="M9 12h6M9 16h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M15 12l1.5 1.5L19 11" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        // FAZA 2: "Firmaga qarz" endi ALOHIDA sahifa emas — u suppliers.html ning
        // "Qarzlar" tabi (ikkalasi bir xil kod nusxasi edi, tuzatish har safar
        // ikki joyda qilinishi kerak bo'lardi va ekranlar bir-biridan uzoqlashardi).
        // Eski `/app/supplier_debt.html` havolasi shu manzilga yo'naltiradi.
        id:      'nav-supplier-debt',
        label:   'Firmaga qarz',
        href:    '/app/suppliers.html?tab=qarzlar',
        feature: Feature.SUPPLIER_DEBT,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="1" y="4" width="22" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M1 10h22" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 15h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <circle cx="7" cy="15" r="1.5" fill="currentColor"/>
                  </svg>`,
    },
    // ── BOSQICH 25: Tovar harakati nav elementlari ────────────────────────────
    {
        id:      'nav-write-offs',
        label:   'Utilizatsiya',
        href:    '/app/write_offs.html',
        feature: Feature.WRITE_OFF,
        roles:   ['admin', 'manager', 'storekeeper'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <polyline points="3 6 5 6 21 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" stroke="currentColor" stroke-width="2"/>
                    <path d="M10 11v6M14 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-goods-regrade',
        label:   'Peresort',
        href:    '/app/goods_regrade.html',
        feature: Feature.GOODS_REGRADE,
        roles:   ['admin', 'manager', 'storekeeper'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M7 16V4m0 0L3 8m4-4l4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M17 8v12m0 0l4-4m-4 4l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-internal-transfers',
        label:   'Ichki ko\'chirish',
        href:    '/app/internal_transfers.html',
        feature: Feature.INTERNAL_TRANSFER,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-loss-report',
        label:   'Zarar hisoboti',
        href:    '/app/loss_report.html',
        feature: Feature.LOSS_REPORT,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M3 3l18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    // ── BOSQICH 26: Narx, Aksiya va Markirovka ───────────────────────────────
    {
        id:      'nav-markup-policy',
        label:   'Naценka siyosati',
        href:    '/app/markup_policy.html',
        feature: Feature.MARKUP_POLICY,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-promotions',
        label:   'Aksiya / Skidka',
        href:    '/app/promotions.html',
        feature: Feature.PROMOTIONS,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" stroke="currentColor" stroke-width="2"/>
                    <circle cx="7" cy="7" r="1.5" fill="currentColor"/>
                  </svg>`,
    },
    {
        id:      'nav-bonus-cards',
        label:   'Bonus kartalar',
        href:    '/app/bonus_cards.html',
        feature: Feature.BONUS_CARD,
        roles:   ['admin', 'manager', 'cashier'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="1" y="4" width="22" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M1 10h22" stroke="currentColor" stroke-width="2"/>
                    <path d="M5 15h4M5 18h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M16 13l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-markirovka',
        label:   "Asl belgisi",
        href:    '/app/markirovka.html',
        feature: Feature.MARKIROVKA,
        roles:   ['admin', 'manager', 'storekeeper'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="3" width="7" height="7" stroke="currentColor" stroke-width="2"/>
                    <rect x="14" y="3" width="7" height="7" stroke="currentColor" stroke-width="2"/>
                    <rect x="3" y="14" width="7" height="7" stroke="currentColor" stroke-width="2"/>
                    <path d="M14 17h2v-2h2v2h2M14 21h2M18 21h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-price-history',
        label:   'Narx tarixi',
        href:    '/app/price_history.html',
        feature: Feature.PRICE_HISTORY,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M3 3v18h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M7 16l4-4 4 4 4-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-vehicles',
        label:   'Auto servis',
        href:    '/app/vehicles.html',
        feature: Feature.SERVICES,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v9a2 2 0 01-2 2h-2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="9" cy="17" r="2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="17" cy="17" r="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M9 9h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-membership',
        label:   "A'zoliklar",
        href:    '/app/membership.html',
        feature: Feature.TIME_BOOKING,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/>
                    <path d="M16 11l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>`,
    },
    {
        id:      'nav-waiter',
        label:   'Ofitsiant panel',
        href:    '/app/waiter.html',
        feature: Feature.WAITER,
        roles:   ['admin', 'waiter', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M18 8h1a4 4 0 010 8h-1" stroke="currentColor" stroke-width="2"/>
                    <path d="M2 8h16v9a4 4 0 01-4 4H6a4 4 0 01-4-4V8z" stroke="currentColor" stroke-width="2"/>
                    <path d="M6 1v3M10 1v3M14 1v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-delivery',
        label:   'Yetkazish',
        href:    '/app/delivery.html',
        feature: Feature.DELIVERY,
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="1" y="3" width="15" height="13" rx="1" stroke="currentColor" stroke-width="2"/>
                    <path d="M16 8h4l3 3v5h-7V8z" stroke="currentColor" stroke-width="2"/>
                    <circle cx="5.5" cy="18.5" r="2.5" stroke="currentColor" stroke-width="2"/>
                    <circle cx="18.5" cy="18.5" r="2.5" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-combo',
        label:   'Kombo menyular',
        href:    '/app/combo.html',
        feature: Feature.COMBO,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="3" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
                    <rect x="14" y="3" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
                    <rect x="3" y="14" width="7" height="7" rx="1" stroke="currentColor" stroke-width="2"/>
                    <path d="M14 17.5h7M17.5 14v7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-happy-hour',
        label:   'Happy Hour',
        href:    '/app/happy_hour.html',
        feature: Feature.HAPPY_HOUR,
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 6v6l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    <path d="M7 20l1-2M17 20l-1-2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-analytics',
        label:   'Analitika',
        href:    '/app/analytics.html',
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-employees',
        label:   'Xodimlar',
        href:    '/app/employees.html',
        roles:   ['admin', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" stroke="currentColor" stroke-width="2"/>
                    <circle cx="9" cy="7" r="4" stroke="currentColor" stroke-width="2"/>
                    <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
    {
        id:      'nav-shift',
        label:   'Smena',
        href:    '/app/shift.html',
        roles:   ['admin', 'cashier', 'manager'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                  </svg>`,
    },
    {
        id:      'nav-settings',
        label:   'Sozlamalar',
        href:    '/app/settings.html',
        roles:   ['admin'],
        icon:    `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" stroke-width="2"/>
                  </svg>`,
    },
];

// ── Sidebar sinfi ─────────────────────────────────────────────────────────────

class Sidebar {
    static async init(cafeId = null) {
        const auth = new AuthService();
        const user = auth.getCurrentUser?.();

        // Features yuklaymiz
        await features.load(cafeId);

        // Biznes nomi + ikonni yangilaymiz
        const titleEl = document.querySelector('.sidebar-title');
        if (titleEl) {
            titleEl.innerHTML = `${features.getBusinessIcon()} <span>${features.getBusinessLabel()}</span>`;
        }

        // Nav barini to'g'ridan-to'g'ri qo'yamiz (agar sidebar-nav mavjud bo'lsa)
        const nav = document.querySelector('.sidebar-nav');
        if (!nav) return;

        const currentPath = window.location.pathname.replace(/.*\/app\//, '/app/');

        const items = NAV_CONFIG
            .filter(item => {
                // Feature tekshirish
                if (item.feature && !features.isEnabled(item.feature)) return false;
                // Rol tekshirish
                if (item.roles && user) {
                    const userRole = user.role?.name?.toLowerCase() || '';
                    if (!item.roles.includes(userRole)) return false;
                }
                return true;
            })
            .map(item => {
                const isActive = currentPath.endsWith(item.href.replace('/app/', ''));
                return `<a href="${item.href}" class="nav-item${isActive ? ' active' : ''}" id="${item.id}">
                    ${item.icon}
                    <span>${item.label}</span>
                </a>`;
            });

        nav.innerHTML = items.join('');
    }

    /** HTML attributlari (`data-feature`) orqali elementlarni filtrlaymiz */
    static applyToPage() {
        document.querySelectorAll('[data-feature]').forEach(el => {
            const feat = el.dataset.feature;
            const show = features.isEnabled(feat);
            el.style.display = show ? '' : 'none';
            el.setAttribute('aria-hidden', show ? 'false' : 'true');
        });

        document.querySelectorAll('[data-feature-any]').forEach(el => {
            const feats = el.dataset.featureAny.split(',').map(f => f.trim());
            const show  = feats.some(f => features.isEnabled(f));
            el.style.display = show ? '' : 'none';
        });

        document.querySelectorAll('[data-business-type]').forEach(el => {
            const types = el.dataset.businessType.split(',').map(t => t.trim());
            el.style.display = types.includes(features.getBusinessType()) ? '' : 'none';
        });
    }
}

export { Sidebar };
