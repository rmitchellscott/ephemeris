FROM python:3.13-alpine AS builder

RUN apk add --no-cache \
      freetype-dev libjpeg-turbo-dev libpng-dev zlib-dev py3-pillow py3-yaml

WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-alpine

RUN apk add --no-cache \
      freetype libjpeg-turbo libpng poppler-utils py3-pillow py3-yaml

WORKDIR /app
COPY --from=builder /install /usr/local

COPY fonts /app/fonts
COPY assets/cover.pdf /app/assets/cover.pdf
COPY ephemeris.py .

CMD ["python", "ephemeris.py"]
