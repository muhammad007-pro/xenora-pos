/**
 * Feature Flags — client-side (BOSQICH 4.1)
 *
 * Backend `core/feature_flags.py` ning JS akslanmasi.
 * Frontend bu fayl orqali UI elementlarini yoqadi/yashiradi.
 *
 * Ishlatilishi:
 *   import { features } from './features.js';
 *   await features.load();
 *   if (features.isEnabled('kitchen_display')) { ... }
 */

import { API } from './api.js';

// ── Konstanslar ──────────────────────────────────────────────────────────────

export const BusinessType = Object.freeze({
    RESTAURANT:   'restaurant',
    CAFE:         'cafe',
    FAST_FOOD:    'fast_food',
    STORE:        'store',
    SUPERMARKET:  'supermarket',
    PHARMACY:     'pharmacy',
    SALON:        'salon',
    FITNESS:      'fitness',
    AUTO_SERVICE: 'auto_service',
    SCHOOL:       'school',
    HOTEL:        'hotel',
    DRY_CLEANING: 'dry_cleaning',
});

export const Feature = Object.freeze({
    KITCHEN_DISPLAY:     'kitchen_display',
    TABLE_MANAGEMENT:    'table_management',
    WAITER:              'waiter',
    TABLE_RESERVATION:   'table_reservation',
    RECIPE:              'recipe',
    BARCODE:             'barcode',
    SCALE:               'scale',
    EXPIRY_DATE:         'expiry_date',
    TIME_BOOKING:        'time_booking',
    SERVICES:            'services',
    INVENTORY:           'inventory',
    LOYALTY:             'loyalty',
    DELIVERY:            'delivery',
    QR_MENU:             'qr_menu',
    // Pro funksiyalar (BOSQICH 9)
    MODIFIERS:           'modifiers',
    COMBO:               'combo',
    HAPPY_HOUR:          'happy_hour',
    TABLE_MERGE:         'table_merge',
    COURSES:             'courses',
    WAITER_CALL:         'waiter_call',
    TIPS:                'tips',
    CUSTOMER_HISTORY:    'customer_history',
    VOICE_ORDER:         'voice_order',
    // BOSQICH 17: Poteriya
    YIELD_TRACKING:      'yield_tracking',
    // BOSQICH 18: Xodimlar ovqati
    STAFF_MEAL:          'staff_meal',
    // BOSQICH 19: Magazin Pro
    CREDIT_SALES:        'credit_sales',
    WHOLESALE_PRICING:   'wholesale_pricing',
    RETURNS:             'returns',
    // BOSQICH 20: Magazin Pro II
    PROMOTIONS:          'promotions',
    MULTI_BARCODE:       'multi_barcode',
    QUICK_SELL:          'quick_sell',
    SUPPLIER_ACCOUNTING: 'supplier_accounting',
    PRICE_HISTORY:       'price_history',
    RECEIPT_SETTINGS:    'receipt_settings',
    CASH_REGISTER:       'cash_register',
    DEPARTMENTS:         'departments',
    // BOSQICH 22: Dorixona maxsus
    PRESCRIPTION_ARCHIVE: 'prescription_archive',
    DRUG_ANALOGS:         'drug_analogs',
    BATCH_TRACKING:       'batch_tracking',
    DOSAGE_INFO:          'dosage_info',
    RX_REQUIRED:          'rx_required',
    // BOSQICH 23: Salon maxsus
    ONLINE_BOOKING:       'online_booking',
    STAFF_SCHEDULE:       'staff_schedule',
    BEFORE_AFTER_PHOTO:   'before_after_photo',
    SALON_CLIENT_HISTORY: 'salon_client_history',
    COMMISSION_REPORT:    'commission_report',
    // BOSQICH 24: Magazin B2B oldi-berdi
    SUPPLIER_CARD:        'supplier_card',
    PURCHASE_RECEIPT:     'purchase_receipt',
    SUPPLIER_DEBT:        'supplier_debt',
    SUPPLIER_RETURN:      'supplier_return',
    // BOSQICH 25: Tovar harakati va hisobdan chiqarish
    WRITE_OFF:            'write_off',
    GOODS_REGRADE:        'goods_regrade',
    CUSTOMER_RETURN_EXT:  'customer_return_ext',
    INTERNAL_TRANSFER:    'internal_transfer',
    LOSS_REPORT:          'loss_report',
    // BOSQICH 26: Narx, Aksiya va Markirovka
    MARKUP_POLICY:        'markup_policy',
    BONUS_CARD:           'bonus_card',
    MARKIROVKA:           'markirovka',
});

// Backend `BUSINESS_FEATURE_MATRIX` ning JS nusxasi (offline fallback uchun)
const FEATURE_MATRIX = {
    [BusinessType.RESTAURANT]: [
        Feature.KITCHEN_DISPLAY, Feature.TABLE_MANAGEMENT, Feature.WAITER,
        Feature.TABLE_RESERVATION, Feature.RECIPE, Feature.SCALE,
        Feature.INVENTORY, Feature.LOYALTY, Feature.DELIVERY, Feature.QR_MENU,
        Feature.MODIFIERS, Feature.COMBO, Feature.HAPPY_HOUR, Feature.TABLE_MERGE,
        Feature.COURSES, Feature.WAITER_CALL, Feature.TIPS, Feature.CUSTOMER_HISTORY,
        Feature.VOICE_ORDER, Feature.YIELD_TRACKING, Feature.STAFF_MEAL,
    ],
    [BusinessType.CAFE]: [
        Feature.KITCHEN_DISPLAY, Feature.TABLE_MANAGEMENT, Feature.WAITER,
        Feature.RECIPE, Feature.SCALE, Feature.INVENTORY, Feature.LOYALTY, Feature.QR_MENU,
        Feature.MODIFIERS, Feature.HAPPY_HOUR, Feature.WAITER_CALL, Feature.TIPS,
        Feature.CUSTOMER_HISTORY, Feature.VOICE_ORDER,
        Feature.YIELD_TRACKING, Feature.STAFF_MEAL,
    ],
    [BusinessType.FAST_FOOD]: [
        Feature.KITCHEN_DISPLAY, Feature.RECIPE, Feature.INVENTORY,
        Feature.LOYALTY, Feature.DELIVERY, Feature.COMBO, Feature.MODIFIERS,
        Feature.VOICE_ORDER, Feature.YIELD_TRACKING, Feature.STAFF_MEAL,
    ],
    [BusinessType.STORE]: [
        Feature.BARCODE, Feature.SCALE, Feature.INVENTORY, Feature.LOYALTY,
        Feature.CREDIT_SALES, Feature.WHOLESALE_PRICING, Feature.RETURNS,
        Feature.PROMOTIONS, Feature.MULTI_BARCODE, Feature.QUICK_SELL,
        Feature.PRICE_HISTORY,
        Feature.RECEIPT_SETTINGS, Feature.CASH_REGISTER, Feature.DEPARTMENTS,
        // BOSQICH 24: Firma (FREE) — supplier_accounting PRO qoladi (backend bilan mos)
        Feature.SUPPLIER_CARD, Feature.PURCHASE_RECEIPT, Feature.SUPPLIER_DEBT, Feature.SUPPLIER_RETURN,
        // BOSQICH 25: Tovar harakati
        Feature.WRITE_OFF, Feature.GOODS_REGRADE, Feature.CUSTOMER_RETURN_EXT,
        Feature.INTERNAL_TRANSFER, Feature.LOSS_REPORT,
        // BOSQICH 26: Narx, Aksiya va Markirovka
        Feature.MARKUP_POLICY, Feature.BONUS_CARD, Feature.MARKIROVKA,
    ],
    [BusinessType.SUPERMARKET]: [
        Feature.BARCODE, Feature.SCALE, Feature.INVENTORY, Feature.LOYALTY,
        Feature.CREDIT_SALES, Feature.WHOLESALE_PRICING, Feature.RETURNS,
        Feature.PROMOTIONS, Feature.MULTI_BARCODE, Feature.QUICK_SELL,
        Feature.PRICE_HISTORY,
        Feature.RECEIPT_SETTINGS, Feature.CASH_REGISTER, Feature.DEPARTMENTS,
        // BOSQICH 24: Firma (FREE) — supplier_accounting PRO qoladi (backend bilan mos)
        Feature.SUPPLIER_CARD, Feature.PURCHASE_RECEIPT, Feature.SUPPLIER_DEBT, Feature.SUPPLIER_RETURN,
        // BOSQICH 25: Tovar harakati
        Feature.WRITE_OFF, Feature.GOODS_REGRADE, Feature.CUSTOMER_RETURN_EXT,
        Feature.INTERNAL_TRANSFER, Feature.LOSS_REPORT,
        // BOSQICH 26: Narx, Aksiya va Markirovka
        Feature.MARKUP_POLICY, Feature.BONUS_CARD, Feature.MARKIROVKA,
    ],
    [BusinessType.PHARMACY]: [
        Feature.BARCODE, Feature.EXPIRY_DATE, Feature.INVENTORY, Feature.LOYALTY,
        Feature.RETURNS, Feature.RECEIPT_SETTINGS, Feature.CASH_REGISTER,
        Feature.PRICE_HISTORY,   // supplier_accounting (PRO) default'dan olib tashlandi — backend bilan mos
        Feature.PRESCRIPTION_ARCHIVE, Feature.DRUG_ANALOGS,
        Feature.BATCH_TRACKING, Feature.DOSAGE_INFO, Feature.RX_REQUIRED,
    ],
    [BusinessType.SALON]: [
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY, Feature.LOYALTY,
        Feature.CUSTOMER_HISTORY,
        // BOSQICH 23
        Feature.ONLINE_BOOKING, Feature.STAFF_SCHEDULE, Feature.BEFORE_AFTER_PHOTO,
        Feature.SALON_CLIENT_HISTORY, Feature.COMMISSION_REPORT,
    ],
    [BusinessType.FITNESS]: [
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.LOYALTY,
    ],
    [BusinessType.AUTO_SERVICE]: [
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY,
    ],
    [BusinessType.SCHOOL]: [
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.LOYALTY,
    ],
    [BusinessType.HOTEL]: [
        Feature.TABLE_RESERVATION, Feature.TIME_BOOKING, Feature.SERVICES,
        Feature.INVENTORY, Feature.LOYALTY,
    ],
    [BusinessType.DRY_CLEANING]: [
        Feature.TIME_BOOKING, Feature.SERVICES, Feature.INVENTORY,
    ],
};

// Biznes turi → UI uchun chiroyli nom + emoji
export const BUSINESS_LABELS = {
    [BusinessType.RESTAURANT]:   { label: 'Restoran',        icon: '🍽️' },
    [BusinessType.CAFE]:         { label: 'Kafe',            icon: '☕' },
    [BusinessType.FAST_FOOD]:    { label: 'Fast Food',       icon: '🍔' },
    [BusinessType.STORE]:        { label: 'Magazin',         icon: '🏪' },
    [BusinessType.SUPERMARKET]:  { label: 'Supermarket',     icon: '🛒' },
    [BusinessType.PHARMACY]:     { label: 'Dorixona',        icon: '💊' },
    [BusinessType.SALON]:        { label: "Go'zallik saloni",icon: '💇' },
    [BusinessType.FITNESS]:      { label: 'Fitnes klub',     icon: '💪' },
    [BusinessType.AUTO_SERVICE]: { label: 'Auto servis',     icon: '🔧' },
    [BusinessType.SCHOOL]:       { label: "O'quv markazi",   icon: '📚' },
    [BusinessType.HOTEL]:        { label: 'Mehmonxona',      icon: '🏨' },
    [BusinessType.DRY_CLEANING]: { label: 'Kimyoviy tozalash', icon: '👔' },
};

const CACHE_KEY    = 'restopos_features';
const CACHE_TTL_MS = 5 * 60 * 1000;  // 5 daqiqa

// ── FeatureManager ────────────────────────────────────────────────────────────

class FeatureManager {
    constructor() {
        this._api          = new API();
        this._businessType = BusinessType.CAFE;
        this._enabled      = new Set();
        this._loaded       = false;
    }

    /**
     * Serverdan yoqilgan funksiyalarni yuklab, keshga saqlaydi.
     * Muvaffaqiyatsiz bo'lsa localStorage keshdan yoki standart matrisdan foydalanadi.
     */
    async load(cafeId) {
        // localStorage kesh (TTL tekshiradi)
        const cached = this._readCache();
        if (cached) {
            this._businessType = cached.business_type;
            this._enabled      = new Set(cached.enabled_features);
            this._loaded       = true;
            // Fon yangilanishi
            this._fetchAndCache(cafeId);
            return;
        }

        await this._fetchAndCache(cafeId);
    }

    async _fetchAndCache(cafeId) {
        if (!cafeId) {
            this._loadFromToken();
            return;
        }

        try {
            const res = await this._api.get(`/cafes/${cafeId}/features`);
            if (res.success) {
                this._businessType = res.data.business_type;
                this._enabled      = new Set(res.data.enabled_features);
                this._writeCache({ business_type: res.data.business_type, enabled_features: res.data.enabled_features });
            }
        } catch {
            this._loadFromMatrix();
        }
        this._loaded = true;
    }

    /** JWT tokenidagi cafe_id dan yuklanadi */
    _loadFromToken() {
        try {
            const token   = localStorage.getItem('access_token');
            if (!token) return;
            const payload = JSON.parse(atob(token.split('.')[1]));
            const bt      = payload.business_type || BusinessType.CAFE;
            this._businessType = bt;
            this._enabled      = new Set(FEATURE_MATRIX[bt] || []);
        } catch {
            this._loadFromMatrix();
        }
        this._loaded = true;
    }

    /** Standart matrisan (offline fallback) */
    _loadFromMatrix(businessType = null) {
        const bt          = businessType || this._businessType;
        this._businessType = bt;
        this._enabled      = new Set(FEATURE_MATRIX[bt] || []);
        this._loaded       = true;
    }

    // ── localStorage kesh ────────────────────────────────────────────────

    _readCache() {
        try {
            const raw = localStorage.getItem(CACHE_KEY);
            if (!raw) return null;
            const { data, ts } = JSON.parse(raw);
            if (Date.now() - ts > CACHE_TTL_MS) return null;
            return data;
        } catch { return null; }
    }

    _writeCache(data) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data, ts: Date.now() })); } catch {}
    }

    invalidateCache() {
        localStorage.removeItem(CACHE_KEY);
    }

    // ── Ochiq API ─────────────────────────────────────────────────────────

    isEnabled(feature) {
        return this._enabled.has(feature);
    }

    isAnyEnabled(...featureList) {
        return featureList.some(f => this._enabled.has(f));
    }

    getBusinessType()    { return this._businessType; }
    getBusinessLabel()   { return BUSINESS_LABELS[this._businessType]?.label || this._businessType; }
    getBusinessIcon()    { return BUSINESS_LABELS[this._businessType]?.icon  || '🏢'; }
    getEnabledFeatures() { return [...this._enabled]; }
    isLoaded()           { return this._loaded; }

    /** Funksiyani dinamik yoqish (admin paneldan) */
    enableLocally(feature) {
        this._enabled.add(feature);
        this.invalidateCache();
    }

    disableLocally(feature) {
        this._enabled.delete(feature);
        this.invalidateCache();
    }
}

export const features = new FeatureManager();
