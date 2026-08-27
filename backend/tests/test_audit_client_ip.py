"""Audit jurnalida IP va User-Agent — yozilishi + SOXTALASHTIRISHGA chidamlilik.

MUAMMO (2026-08-27 auditi): `audit_logs.ip_address` ustuni bor edi, `client_ip()`
helper ham yozilgan edi — lekin 18 ta `log_audit()` chaqiruvining BIRORTASI uni
uzatmasdi. Natijada barcha qatorda NULL. Xavfsizlik tekshiruvida "kim qildi"
degan savolga javob yo'q edi.

IKKINCHI, JIDDIYROQ MUAMMO: eski `client_ip()` X-Forwarded-For ning BIRINCHI
bo'g'inini olardi. Bizning nginx `$proxy_add_x_forwarded_for` ishlatadi — u mijoz
yuborgan sarlavhaga haqiqiy IP ni QO'SHIB QO'YADI:

    mijoz:  X-Forwarded-For: 1.2.3.4
    nginx:  X-Forwarded-For: 1.2.3.4, <haqiqiy_ip>
                             ^^^^^^^ mijoz nazoratida!

Ya'ni hujumchi audit jurnalidagi o'z IP sini istalgan qiymatga almashtira olardi
— audit izini soxtalashtirish. Endi X-Real-IP (nginx QAYTA YOZADI) ustun turadi,
XFF dan esa OXIRGI bo'g'in olinadi.

Ishga tushirish:
    cd backend && py -m pytest tests/test_audit_client_ip.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.audit import client_ip


class _Req:
    """Minimal soxta Request (headers + client)."""
    class _Client:
        def __init__(self, host): self.host = host

    def __init__(self, headers=None, host="127.0.0.1"):
        # Starlette headers case-insensitive — shu xulqni takrorlaymiz
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = _Req._Client(host) if host else None

    @property
    def headers(self):
        return self._h


# ══════════════════════════════════════════════════════════════════════════════
# 1) SOXTALASHTIRISH — asosiy xavfsizlik xususiyati
# ══════════════════════════════════════════════════════════════════════════════

def test_xff_birinchi_bogin_soxta_bolsa_olinmaydi():
    """nginx qo'shib qo'ygan holat: mijoz XFF yuborgan, nginx haqiqiy IP ni qo'shgan.

    Eski kod "1.2.3.4" (soxta) qaytarardi. Endi haqiqiy IP olinishi SHART.
    """
    req = _Req({"X-Forwarded-For": "1.2.3.4, 203.0.113.77"})
    assert client_ip(req) == "203.0.113.77", "XFF ning BIRINCHI (soxta) bo'g'ini olindi!"


def test_kop_bosqichli_xff_da_ham_oxirgisi():
    req = _Req({"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3, 203.0.113.77"})
    assert client_ip(req) == "203.0.113.77"


def test_xreal_ip_xff_dan_ustun():
    """nginx X-Real-IP ni $remote_addr bilan QAYTA YOZADI -> ishonchli manba."""
    req = _Req({
        "X-Real-IP": "203.0.113.77",
        "X-Forwarded-For": "6.6.6.6, 7.7.7.7",   # butunlay soxta bo'lsa ham
    })
    assert client_ip(req) == "203.0.113.77"


def test_soxta_xreal_ip_yolgiz_kelsa_ham_nginx_qayta_yozadi():
    """Diqqat: bu birlik testi — himoya nginx darajasida.

    Kod X-Real-IP ga ishonadi, chunki nginx uni HAR DOIM qayta yozadi
    (`proxy_set_header X-Real-IP $remote_addr`). Mijoz yuborgan qiymat
    backendgacha yetib kelmaydi. Test shu shartnomani hujjatlashtiradi.
    """
    req = _Req({"X-Real-IP": "203.0.113.77"})
    assert client_ip(req) == "203.0.113.77"


# ══════════════════════════════════════════════════════════════════════════════
# 2) ODDIY HOLATLAR
# ══════════════════════════════════════════════════════════════════════════════

def test_proxy_sarlavhasiz_togridan_togri_ulanish():
    req = _Req({}, host="198.51.100.9")
    assert client_ip(req) == "198.51.100.9"


def test_yagona_xff_bogini():
    req = _Req({"X-Forwarded-For": "203.0.113.77"})
    assert client_ip(req) == "203.0.113.77"


def test_bosh_qiymatlar_yiqilmaydi():
    assert client_ip(None) is None
    assert client_ip(_Req({"X-Forwarded-For": "  "}, host=None)) is None
    assert client_ip(_Req({"X-Real-IP": ""}, host="10.0.0.1")) == "10.0.0.1"


def test_ipv6_45_belgiga_qirqiladi():
    uzun = "2001:0db8:85a3:0000:0000:8a2e:0370:7334:extra:extra:extra"
    assert len(client_ip(_Req({"X-Real-IP": uzun}))) <= 45


# ══════════════════════════════════════════════════════════════════════════════
# 3) log_audit ContextVar'dan avtomatik o'qiydimi (chaqiruv joyi tegilmasdan)
# ══════════════════════════════════════════════════════════════════════════════

def test_log_audit_contextvardan_ip_va_ua_oladi(monkeypatch):
    """18 ta chaqiruv joyi hech narsa uzatmaydi — middleware o'rnatgani yozilsin."""
    from core.logger import client_ip_var, user_agent_var
    import core.audit as audit_mod

    yozilgan = {}

    class _FakeAuditLog:
        def __init__(self, **kw):
            yozilgan.update(kw)

    class _FakeSession:
        def add(self, obj): pass
        def commit(self): pass
        def close(self): pass

    import models
    monkeypatch.setattr(models, "AuditLog", _FakeAuditLog)
    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: _FakeSession())

    t1 = client_ip_var.set("203.0.113.77")
    t2 = user_agent_var.set("xenora/1.9.5 Electron/27.3.11")
    try:
        # E'TIBOR BER: ip_address / user_agent UZATILMAYDI — mavjud 18 ta
        # chaqiruv joyi aynan shunday chaqiradi.
        audit_mod.log_audit(None, "auth", "LOGIN", 21, tenant_id=26)
    finally:
        client_ip_var.reset(t1)
        user_agent_var.reset(t2)

    assert yozilgan.get("ip_address") == "203.0.113.77", f"IP yozilmadi: {yozilgan}"
    assert yozilgan.get("user_agent") == "xenora/1.9.5 Electron/27.3.11"


def test_aniq_uzatilgan_qiymat_contextvardan_ustun(monkeypatch):
    from core.logger import client_ip_var
    import core.audit as audit_mod

    yozilgan = {}

    class _FakeAuditLog:
        def __init__(self, **kw): yozilgan.update(kw)

    class _FakeSession:
        def add(self, obj): pass
        def commit(self): pass
        def close(self): pass

    import models, database
    monkeypatch.setattr(models, "AuditLog", _FakeAuditLog)
    monkeypatch.setattr(database, "SessionLocal", lambda: _FakeSession())

    t = client_ip_var.set("10.0.0.1")
    try:
        audit_mod.log_audit(None, "orders", "DELETE", 5, ip_address="198.51.100.9")
    finally:
        client_ip_var.reset(t)

    assert yozilgan.get("ip_address") == "198.51.100.9"


def test_uzun_user_agent_255_ga_qirqiladi(monkeypatch):
    from core.logger import user_agent_var
    import core.audit as audit_mod

    yozilgan = {}

    class _FakeAuditLog:
        def __init__(self, **kw): yozilgan.update(kw)

    class _FakeSession:
        def add(self, obj): pass
        def commit(self): pass
        def close(self): pass

    import models, database
    monkeypatch.setattr(models, "AuditLog", _FakeAuditLog)
    monkeypatch.setattr(database, "SessionLocal", lambda: _FakeSession())

    t = user_agent_var.set("X" * 900)
    try:
        audit_mod.log_audit(None, "products", "UPDATE", 1)
    finally:
        user_agent_var.reset(t)

    assert len(yozilgan.get("user_agent")) == 255


def test_soro_konteksti_yoq_bolsa_yiqilmaydi(monkeypatch):
    """Fon vazifasi / CLI — ContextVar bo'sh, audit baribir yozilishi kerak."""
    import core.audit as audit_mod

    yozilgan = {}

    class _FakeAuditLog:
        def __init__(self, **kw): yozilgan.update(kw)

    class _FakeSession:
        def add(self, obj): pass
        def commit(self): pass
        def close(self): pass

    import models, database
    monkeypatch.setattr(models, "AuditLog", _FakeAuditLog)
    monkeypatch.setattr(database, "SessionLocal", lambda: _FakeSession())

    audit_mod.log_audit(None, "shifts", "CREATE", 7)
    assert yozilgan.get("ip_address") is None
    assert yozilgan.get("user_agent") is None
    assert yozilgan.get("resource") == "shifts"
