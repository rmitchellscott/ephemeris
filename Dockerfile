FROM python:3.13-alpine AS builder

RUN apk add --no-cache \
      freetype-dev libjpeg-turbo-dev libpng-dev zlib-dev build-base

WORKDIR /install
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-alpine

RUN apk add --no-cache \
      freetype libjpeg-turbo libpng poppler-utils

WORKDIR /app
COPY --from=builder /install /usr/local

COPY fonts /app/fonts
COPY assets/cover.pdf /app/assets/cover.pdf
COPY ephemeris /app/ephemeris
COPY ephemeris.py .

CMD ["python", "ephemeris.py"]
