#!/bin/sh
# SSL yoqish: nginx.conf ni HTTP-only → HTTPS rejimiga o'tkazadi
# Foydalanish: ./scripts/ssl-enable.sh your.domain.com
set -e

DOMAIN="${1}"
CONF="nginx/nginx.conf"

if [ -z "$DOMAIN" ]; then
    echo "Foydalanish: $0 your.domain.com"
    exit 1
fi

if [ ! -f "$CONF" ]; then
    echo "Xato: $CONF topilmadi. Loyiha root'idan ishga tushiring."
    exit 1
fi

SSL_CERT="/etc/nginx/ssl/live/${DOMAIN}/fullchain.pem"
SSL_KEY="/etc/nginx/ssl/live/${DOMAIN}/privkey.pem"

echo "SSL konfiguratsiyasi yoqilmoqda: $DOMAIN"

# 1. HTTP server blokiga redirect qo'shish
sed -i "s|# location / {|location / {|" "$CONF"
sed -i "s|#     return 301 https://\$host\$request_uri;|    return 301 https://\$host\$request_uri;|" "$CONF"
sed -i "s|# }  # HTTP redirect|} # HTTP redirect|" "$CONF"

# 2. HTTPS server blokini uncomment qilish
python3 - <<PYEOF
import re

with open('$CONF', 'r') as f:
    content = f.read()

# HTTPS server blokini uncomment qilish
https_block = content.find('# ─── HTTPS server')
if https_block == -1:
    print("HTTPS bloki topilmadi — nginx.conf ni qo'lda tahrirlang")
    exit(1)

# Barcha comment'larni olib tashlash (server blok ichida)
def uncomment_block(text):
    lines = text.split('\n')
    result = []
    in_https_block = False
    for line in lines:
        if '─── HTTPS server' in line:
            in_https_block = True
        if in_https_block and line.strip().startswith('#'):
            line = line.replace('# ', '', 1).replace('#', '', 1)
        if in_https_block and line.strip() == '# }':
            line = line.replace('# }', '}')
            in_https_block = False
        result.append(line)
    return '\n'.join(result)

content = uncomment_block(content)
# Domen nomini almashtirish
content = content.replace('your.domain.com', '$DOMAIN')

with open('$CONF', 'w') as f:
    f.write(content)

print("nginx.conf yangilandi")
PYEOF

echo ""
echo "Tayyor! Hozir nginx ni qayta ishga tushiring:"
echo "  make restart"
echo ""
echo "HSTS tekshirish: curl -I https://$DOMAIN"
