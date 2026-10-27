# php-fpm (VPS)

Os quatro apps Laravel rodam no php-fpm 8.4, um pool por app, no lugar do
`php artisan serve`. O Caddy (`deploy/caddy/php.caddy`) atende em 127.0.0.1
nas portas antigas (8000 Fluent, 8001 Engine, 8003 Express, 8004 ACT) e repassa
ao socket `/run/php/enquire-<app>.sock`.

## Instalação

```bash
cp deploy/php-fpm/enquire-*.conf /etc/php/8.4/fpm/pool.d/
mkdir -p /var/log/php-fpm && chown www-data:www-data /var/log/php-fpm
# Os pools rodam como www-data; fila e deploy continuam como root.
# ACL padrão: arquivos criados pelo root nessas pastas continuam graváveis.
apt-get install -y acl
for d in /var/www/enquire-survey /var/www/enquire-survey-engine \
         /var/www/enquire-act-express/act /var/www/enquire-act-express/express; do
  setfacl -R -m u:www-data:rwX -m d:u:www-data:rwX $d/storage $d/bootstrap/cache
  setfacl -m u:www-data:r $d/.env
done
mkdir -p /var/www/enquire-act-express/express/public/gallery
setfacl -R -m u:www-data:rwX -m d:u:www-data:rwX /var/www/enquire-act-express/express/public/gallery
systemctl reload php8.4-fpm
systemctl disable --now enquire-survey enquire-survey-engine enquire-express enquire-act
```

## Deploy

Depois de `git pull` + `composer install` + `php artisan optimize:clear`,
recarregar o php-fpm (opcache): `systemctl reload php8.4-fpm`.
A fila (`enquire-survey-queue`) continua com `systemctl restart`.

Logs de erro do PHP: `/var/log/php-fpm/enquire-<app>.log`.
