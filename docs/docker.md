# Running nanogateway in Docker

You'll typically run nanogateway as a sidecar to your own app. Copy whichever pattern fits.

## Sidecar via docker compose

```yaml
services:
  gateway:
    image: nanogateway   # build & push your own, or use a local build
    ports:
      - "9000:9000"
    environment:
      NANOGATEWAY_URL: https://api.openai.com/v1
    volumes:
      - nanogw-data:/app/.nanogateway

  app:
    build: ./your-app
    environment:
      OPENAI_BASE_URL: http://gateway:9000/v1
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - gateway

volumes:
  nanogw-data:
```

Your app points its OpenAI client at `http://gateway:9000/v1`. The gateway forwards the client's `Authorization` header upstream — so the app uses its real provider key normally; the gateway doesn't see it stored anywhere.

Every call is logged in the gateway and viewable at <http://localhost:9000>.

## Inlining into your app's image

If you don't want a separate container, install inside your own Dockerfile:

```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir nanogateway
ENV NANOGATEWAY_URL=https://api.openai.com/v1
EXPOSE 9000
CMD ["nanogateway", "serve", "--port", "9000"]
```

Same env var as above. Use a single entrypoint or run both processes under a supervisor.

## Building the image yourself

There's no published `nanogateway` image today. Until you push one, build locally:

```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir nanogateway
ENV PYTHONUNBUFFERED=1
USER 1000
EXPOSE 9000
ENTRYPOINT ["nanogateway"]
CMD ["serve", "--port", "9000"]
```

Build and tag it:

```bash
docker build -t nanogateway:local .
```

Then reference `image: nanogateway:local` in compose.

## Persisting the SQLite DB

Default path is `.nanogateway/data.db` relative to the working directory. To keep traces across restarts:

```yaml
volumes:
  - nanogw-data:/app/.nanogateway
```

```bash
docker run -v nanogw-data:/app/.nanogateway ...
```

Mount the directory, not the file. There's no log rotation — the DB grows unbounded. Prune the volume when you're done debugging.

## Env vars

Only one gateway env var is needed: `NANOGATEWAY_URL`. The client uses its own `OPENAI_BASE_URL` and `OPENAI_API_KEY` like any normal OpenAI setup. See [Config](config.md).
