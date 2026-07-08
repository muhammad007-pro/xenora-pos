"""
Printer uchun yordamchi funksiyalar
"""

import os
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import settings


def format_receipt(order_data: Dict[str, Any], payment_data: Dict[str, Any] = None) -> str:
    """Chek matnini formatlash"""
    lines = []
    width = 40  # Printer qog'oz kengligi
    
    # Sarlavha
    lines.append("=" * width)
    lines.append(center_text("PREMIUM RESTAURANT", width))
    lines.append(center_text("Sizning tanlovingiz biz uchun muhim!", width))
    lines.append("=" * width)
    
    # Buyurtma ma'lumotlari
    order_number = order_data.get("order_number", "-")
    lines.append(f"Chek: #{order_number}")
    lines.append(f"Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    if order_data.get("table_number"):
        lines.append(f"Stol: #{order_data['table_number']}")
    
    if order_data.get("waiter_name"):
        lines.append(f"Ofitsiant: {order_data['waiter_name']}")
    
    lines.append("-" * width)
    
    # Mahsulotlar
    lines.append(f"{'Mahsulot':<20}{'Soni':>7}{'Summa':>13}")
    lines.append("-" * width)
    
    items = order_data.get("items", [])
    for item in items:
        name = item.get("product_name", "")[:18]
        qty = item.get("quantity", 1)
        price = item.get("total_price", 0)
        
        lines.append(f"{name:<20}{qty:>7}{format_price(price):>13}")
        
        if item.get("notes"):
            lines.append(f"  * {item['notes'][:30]}")
    
    lines.append("-" * width)
    
    # Jami
    subtotal = order_data.get("total_amount", 0)
    discount = order_data.get("discount_amount", 0)
    tax = order_data.get("tax_amount", 0)
    service = order_data.get("service_charge", 0)
    total = order_data.get("final_amount", subtotal)
    
    lines.append(f"{'Jami:':<27}{format_price(subtotal):>13}")
    
    if discount > 0:
        lines.append(f"{'Chegirma:':<27}{'-' + format_price(discount):>13}")
    
    if tax > 0:
        lines.append(f"{'Soliq (12%):':<27}{format_price(tax):>13}")
    
    if service > 0:
        lines.append(f"{'Xizmat (10%):':<27}{format_price(service):>13}")
    
    lines.append("=" * width)
    lines.append(f"{'UMUMIY:':<27}{format_price(total):>13}")
    lines.append("=" * width)
    
    # To'lov
    if payment_data:
        method = payment_data.get("method", "-")
        method_names = {"cash": "Naqd", "card": "Karta", "click": "Click", "payme": "Payme"}
        lines.append(f"To'lov: {method_names.get(method, method)}")
        
        if method == "cash" and payment_data.get("cash_received"):
            received = payment_data["cash_received"]
            change = received - total
            lines.append(f"Qabul qilindi: {format_price(received)}")
            lines.append(f"Qaytim: {format_price(change)}")
    
    lines.append("=" * width)
    lines.append(center_text("Xaridingiz uchun rahmat!", width))
    lines.append(center_text("Yana tashrif buyurishingizni kutamiz!", width))
    lines.append("=" * width)

    # ── Fiskal QR blok ────────────────────────────────────────────────────────
    fiscal_qr_url    = order_data.get("fiscal_qr_url")
    fiscal_number    = order_data.get("fiscal_number")
    if fiscal_qr_url:
        lines.append("")
        lines.append(center_text("FISKAL CHEK", width))
        lines.append(center_text("Soliq ilovasida skanerlang", width))
        if fiscal_number:
            lines.append(center_text(f"Chek #{fiscal_number}", width))
        # ESC/POS printerlar uchun QR — GS ( k buyrug'i bilan
        # (agar printer ESC/POS formatini qabul qilsa, shu yerda bytes qo'shiladi)
        # Matnli printer uchun qisqartirilgan URL ko'rsatamiz
        short_url = fiscal_qr_url[:width] if len(fiscal_qr_url) > width else fiscal_qr_url
        lines.append(short_url)
        if len(fiscal_qr_url) > width:
            lines.append(fiscal_qr_url[width:width*2])
        lines.append(center_text("1% keshbek olishingiz mumkin", width))
        lines.append("")

    # QR kod uchun joy
    lines.append("")
    lines.append("")

    # Kesish chizig'i
    lines.append("-" * width)
    lines.append("")

    return "\n".join(lines)


def format_kitchen_order(order_data: Dict[str, Any]) -> str:
    """Oshxona buyurtmasi matnini formatlash"""
    lines = []
    width = 40
    
    lines.append("=" * width)
    lines.append(center_text("OSHXONA BUYURTMASI", width))
    lines.append("=" * width)
    
    lines.append(f"Buyurtma: #{order_data.get('order_number')}")
    lines.append(f"Stol: {order_data.get('table_number', 'Olib ketish')}")
    lines.append(f"Ofitsiant: {order_data.get('waiter_name', '-')}")
    lines.append(f"Vaqt: {datetime.now().strftime('%H:%M:%S')}")
    lines.append("-" * width)
    
    items = order_data.get("items", [])
    for item in items:
        name = item.get("product_name", "")[:30]
        qty = item.get("quantity", 1)
        lines.append(f"{qty} x {name}")
        
        if item.get("notes"):
            lines.append(f"    * {item['notes'][:30]}")
    
    lines.append("-" * width)
    
    if order_data.get("notes"):
        lines.append(f"IZOH: {order_data['notes']}")
        lines.append("-" * width)
    
    lines.append("")
    lines.append("")
    lines.append("")
    lines.append("-" * width)
    
    return "\n".join(lines)


def format_report(report_data: Dict[str, Any], report_type: str) -> str:
    """Hisobot matnini formatlash"""
    lines = []
    width = 40
    
    lines.append("=" * width)
    
    titles = {
        "daily": "KUNLIK HISOBOT",
        "shift": "SMENA HISOBOTI",
        "sales": "SAVDO HISOBOTI"
    }
    
    lines.append(center_text(titles.get(report_type, "HISOBOT"), width))
    lines.append("=" * width)
    lines.append(f"Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    lines.append("-" * width)
    
    if report_type == "daily":
        lines.append(f"Jami savdo: {format_price(report_data.get('total_sales', 0))}")
        lines.append(f"Naqd: {format_price(report_data.get('cash_sales', 0))}")
        lines.append(f"Karta: {format_price(report_data.get('card_sales', 0))}")
        lines.append(f"Buyurtmalar: {report_data.get('orders_count', 0)}")
        lines.append(f"O'rtacha chek: {format_price(report_data.get('avg_check', 0))}")
    
    elif report_type == "shift":
        lines.append(f"Smena ochildi: {report_data.get('start_time', '-')}")
        lines.append(f"Smena yopildi: {report_data.get('end_time', '-')}")
        lines.append(f"Boshlang'ich kassa: {format_price(report_data.get('starting_cash', 0))}")
        lines.append(f"Yakuniy kassa: {format_price(report_data.get('ending_cash', 0))}")
        lines.append(f"Jami savdo: {format_price(report_data.get('total_sales', 0))}")
    
    lines.append("=" * width)
    lines.append("")
    lines.append("")
    lines.append("-" * width)
    
    return "\n".join(lines)


def center_text(text: str, width: int) -> str:
    """Matnni o'rtaga joylashtirish"""
    if len(text) >= width:
        return text[:width]
    
    padding = (width - len(text)) // 2
    return " " * padding + text


def format_price(price: float) -> str:
    """Narxni formatlash"""
    return f"{price:,.0f}".replace(",", " ")


def print_receipt(content: str) -> bool:
    """Chekni chop etish"""
    if not settings.PRINTER_ENABLED:
        print("[PRINTER] Printer o'chirilgan")
        return False
    
    try:
        # Faylga saqlash
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"static/receipts/receipt_{timestamp}.txt"
        
        os.makedirs("static/receipts", exist_ok=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Printerga yuborish
        if settings.PRINTER_PORT:
            try:
                if os.name == 'nt':
                    subprocess.run(['print', f'/D:{settings.PRINTER_PORT}', filename], 
                                 capture_output=True, shell=True)
                else:
                    with open(settings.PRINTER_PORT, 'wb') as printer:
                        printer.write(content.encode('utf-8'))
            except Exception as e:
                print(f"[PRINTER] Printerga yuborishda xatolik: {e}")
        
        return True
        
    except Exception as e:
        print(f"[PRINTER] Xatolik: {e}")
        return False


def print_kitchen_order(content: str) -> bool:
    """Oshxona buyurtmasini chop etish"""
    if not settings.PRINTER_ENABLED:
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"static/receipts/kitchen_{timestamp}.txt"
    
    os.makedirs("static/receipts", exist_ok=True)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    return True


def test_printer() -> Dict[str, Any]:
    """Printerni test qilish"""
    test_content = "\n" + "=" * 40 + "\n"
    test_content += center_text("PRINTER TEST", 40) + "\n"
    test_content += "=" * 40 + "\n"
    test_content += center_text("Agar bu matn chiqqan bo'lsa,", 40) + "\n"
    test_content += center_text("printer to'g'ri ishlayapti!", 40) + "\n"
    test_content += "=" * 40 + "\n\n\n"
    
    success = print_receipt(test_content)
    
    return {
        "success": success,
        "printer_enabled": settings.PRINTER_ENABLED,
        "printer_port": settings.PRINTER_PORT if settings.PRINTER_ENABLED else None
    }