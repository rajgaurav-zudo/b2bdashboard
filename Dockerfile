# Production image: one container serving the API and the built frontend.
#
# One deployable rather than two means one origin, so there is no CORS to
# configure and no second service to keep in step. The dashboards directory is
# copied in, so a dashboard ships with the image it was tested against.

# --- build the frontend -------------------------------------------------------
FROM node:20-alpine AS web

WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# Vite inlines these at build time, so they are baked into the bundle rather than
# read at boot. Both are public by design: the anon key reaches the sign-in
# endpoints and nothing else, because every data route verifies the token
# server-side. The service role key is never named VITE_* and so cannot land here.
ARG VITE_SUPABASE_URL=""
ARG VITE_SUPABASE_ANON_KEY=""
ARG VITE_AUTH_REQUIRED="true"
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_AUTH_REQUIRED=$VITE_AUTH_REQUIRED
RUN npm run build

# --- runtime ------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv/api

COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ /srv/api/
COPY dashboards/ /srv/dashboards/
COPY sources/ /srv/sources/
COPY --from=web /build/dist /srv/web

ENV DASHBOARDS_DIR=/srv/dashboards \
    SOURCES_FILE=/srv/sources/sources.yaml \
    WEB_DIST=/srv/web \
    UPLOAD_DIR=/srv/data/uploads \
    AUTH_REQUIRED=true

# no --reload, and a worker count the platform can override
ENV WEB_CONCURRENCY=2
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
