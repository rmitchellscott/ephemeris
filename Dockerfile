FROM python:3.13-alpine

RUN apk add --no-cache \
      freetype libjpeg-turbo libpng poppler-utils \
    && apk add --no-cache --virtual .build-deps \
      build-base zlib-dev libjpeg-turbo-dev libpng-dev freetype-dev

WORKDIR /app
COPY fonts /app/fonts
COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

RUN apk del .build-deps \
 && rm -rf /var/cache/apk/*

COPY ephemeris.py .
CMD ["python", "ephemeris.py"]
