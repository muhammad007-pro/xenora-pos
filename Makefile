# RestoPOS — Docker buyruqlari
# Foydalanish: make <buyruq> [parametr=qiymat]

.PHONY: up down build restart logs ps migrate shell db clean setup test \
        ssl-init ssl-renew ssl-enable

# ─── Asosiy buyruqlar ─────────────────────────────────────────────────────────

setup:
	cp backend/.env.docker backend/.env
	@echo "backend/.env yaratildi — SECRET_KEY ni o'zgartiring!"

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build --no-cache

restart:
	docker-compose restart

logs:
	docker-compose logs -f

ps:
	docker-compose ps

# ─── Backend ──────────────────────────────────────────────────────────────────

migrate:
	docker-compose exec backend alembic upgrade head

shell:
	docker-compose exec backend bash

db:
	docker-compose exec db psql -U pos_user -d restaurant_pos

test:
	cd backend && python -m pytest tests/ -v

# ─── SSL / Let's Encrypt ──────────────────────────────────────────────────────
# Birinchi marta: make ssl-init domain=your.domain.com email=admin@domain.com
# Yangilash:      make ssl-renew
# SSL yoqish (nginx.conf ichidagi SSL blokni uncomment qilib):
#                 make ssl-enable domain=your.domain.com

ssl-init:
	@if [ -z "$(domain)" ]; then echo "Foydalanish: make ssl-init domain=your.domain.com email=admin@domain.com"; exit 1; fi
	@if [ -z "$(email)" ]; then echo "Foydalanish: make ssl-init domain=your.domain.com email=admin@domain.com"; exit 1; fi
	docker-compose run --rm certbot certonly \
		--webroot \
		--webroot-path=/var/www/certbot \
		--email $(email) \
		--agree-tos \
		--no-eff-email \
		-d $(domain) \
		-d www.$(domain)
	@echo ""
	@echo "SSL sertifikati olindi! Quyidagi qadamlarni bajaring:"
	@echo "1. nginx/nginx.conf da HTTPS server blokini uncomment qiling"
	@echo "2. HTTP redirect blokini yoqing"
	@echo "3. server_name ni '$(domain)' ga o'zgartiring"
	@echo "4. make restart"

ssl-renew:
	docker-compose --profile ssl run --rm certbot renew --quiet
	docker-compose exec nginx nginx -s reload

ssl-enable:
	@if [ -z "$(domain)" ]; then echo "Foydalanish: make ssl-enable domain=your.domain.com"; exit 1; fi
	@echo "nginx/nginx.conf ni qo'lda tahrirlash kerak — SSL blokini uncomment qiling va '$(domain)' ni kiriting"
	@echo "Yoki scripts/ssl-enable.sh skriptini ishlating"

# ─── Tozalash ─────────────────────────────────────────────────────────────────

clean:
	docker-compose down -v --remove-orphans
