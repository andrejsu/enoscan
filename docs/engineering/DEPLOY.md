# Деплой на VPS

Каждый push в `master` запускает `.github/workflows/deploy.yml`:

1. `check` — `npm run check`.
2. `build` — образы `web`, `importer`, `retriever` собираются в GitHub Actions и публикуются в GHCR с тегами `<sha>` и `latest`. На сервере ничего не собирается.
3. `deploy` — по SSH копирует `deploy/compose.prod.yaml`, `deploy/Caddyfile` и `db/` в `/opt/vinolog`, затем выполняет `docker compose pull` и `up -d` и ждёт, пока `web` станет healthy.

Ручной запуск: Actions → deploy → Run workflow.

Прод-стек: `db`, `minio`, `retriever`, `ranking`, `web`, `caddy` плюс однократные `importer`, `retriever-model`, `retriever-index`. Наружу открыт только Caddy (80/443). Сервисы `retrieval`, `retrieval-index` и `ocr-retriever` из dev-compose в прод не входят.

Ресурсы: 4 vCPU, 8 ГБ RAM, от 40 ГБ диска, архитектура amd64. GPU не нужен.

## Однократная настройка сервера

Команды для Ubuntu/Debian, выполняются под root.

```bash
curl -fsSL https://get.docker.com | sh
adduser --disabled-password --gecos '' deploy
usermod -aG docker deploy
mkdir -p /opt/vinolog/data/dataset && chown -R deploy:deploy /opt/vinolog
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443 && ufw enable
```

Членство в группе `docker` фактически даёт root. Используйте отдельного пользователя и ключ только для деплоя.

### SSH-ключ для GitHub Actions

На своей машине:

```bash
ssh-keygen -t ed25519 -N '' -C vinolog-deploy -f ~/.ssh/vinolog_deploy
ssh-copy-id -i ~/.ssh/vinolog_deploy.pub deploy@<IP>
ssh-keyscan -t ed25519 <IP>
```

### `.env` на сервере

Скопируйте `deploy/.env.production.example` в `/opt/vinolog/.env` и замените секреты (`openssl rand -hex 24`). Без этого файла деплой остановится с ошибкой. Пароли PostgreSQL и MinIO задаются при первом старте томов: если позже поменять их в `.env`, придётся менять их и внутри сервисов.

Когда A-запись домена будет указывать на VPS, укажите `VINOLOG_DOMAIN=vinolog.example.ru`: Caddy сам выпустит сертификат Let's Encrypt. Без домена сайт открывается по HTTP на IP сервера, а камера в мобильных браузерах требует HTTPS.

### Датасет

Датасет не хранится в git и загружается один раз:

```bash
rsync -avP data/dataset/ deploy@<IP>:/opt/vinolog/data/dataset/
```

Первый деплой импортирует каталог и строит индекс ретривера, это около 15 минут. Следующие деплои видят ту же версию данных и пропускают эти шаги. Чтобы обновить каталог, загрузите новые файлы тем же `rsync` и перезапустите workflow.

## Настройки GitHub

Settings → Environments → создайте `production` и добавьте секреты:

| Секрет | Значение |
|---|---|
| `VPS_HOST` | IP или домен сервера |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | содержимое `~/.ssh/vinolog_deploy` (приватный ключ) |
| `VPS_KNOWN_HOSTS` | вывод `ssh-keyscan` |

Необязательные переменные окружения (Variables): `VPS_PORT` (по умолчанию `22`) и `DEPLOY_PATH` (по умолчанию `/opt/vinolog`).

В environment `production` можно включить Required reviewers, чтобы деплой ждал подтверждения.

Образы в GHCR приватные, если приватный репозиторий. Сервер логинится в GHCR одноразовым `GITHUB_TOKEN` только на время деплоя.

## Эксплуатация

```bash
cd /opt/vinolog
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs -f --tail 100 web ranking
docker compose -f compose.prod.yaml up -d --force-recreate web   # после правки .env
```

Откат: Actions → выберите успешный прошлый запуск → Re-run jobs. Либо на сервере:

```bash
IMAGE_TAG=<sha> docker compose -f compose.prod.yaml up -d
```

Бэкап БД:

```bash
docker compose -f compose.prod.yaml exec -T db pg_dump -U vinolog vinolog | gzip > vinolog-$(date +%F).sql.gz
```
