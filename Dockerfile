# One Dockerfile, two images: "backend" (Flask) and "web" (Apache + the built React site). compose.yaml builds both.

# Builds the React site. The API address is left empty so the site calls the address it was opened from.
FROM node:24-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Public keys for the map and Stripe's card field are baked into the site at build time (both optional).
ARG VITE_MAPBOX_ACCESS_TOKEN=
ARG VITE_STRIPE_PUBLISHABLE_KEY=
ENV VITE_API_BASE=
RUN npm run build

# The web image: Apache serves the build and forwards /api to the backend container.
FROM httpd:2.4-alpine AS web
RUN sed -i \
      -e 's|^#\(LoadModule proxy_module .*\)|\1|' \
      -e 's|^#\(LoadModule proxy_http_module .*\)|\1|' \
      -e 's|^#\(LoadModule rewrite_module .*\)|\1|' \
      /usr/local/apache2/conf/httpd.conf \
 && echo "Include conf/ofs.conf" >> /usr/local/apache2/conf/httpd.conf
COPY docker/ofs-web.conf /usr/local/apache2/conf/ofs.conf
COPY --from=frontend-build /app/frontend/dist/ /usr/local/apache2/htdocs/

# The backend image: Flask served by Waitress (a production-style server), as a normal user.
FROM python:3.12-slim AS backend
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt waitress==3.0.0
COPY backend/ ./backend/
RUN useradd --create-home ofs && chown -R ofs:ofs /app
USER ofs
WORKDIR /app/backend
EXPOSE 5001
CMD ["waitress-serve", "--listen=0.0.0.0:5001", "app:app"]
