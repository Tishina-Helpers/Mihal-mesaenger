# Михаль — Messenger & Cesium Flight (MVP)

Responsive FastAPI starter: accounts, contact search, direct messages, groups/channels, built-in Groq assistant, Cloudflare image generation, OpenWeather current/forecast, and CesiumJS globe with prototype flight controls.

## Render setup
Build command: `pip install -r requirements.txt`
Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
Health endpoint: `/api/health`

Set Render Environment variables:
- `DATABASE_URL` — MongoDB connection string
- `MONGODB_DB_NAME` — `mikhal_messenger`
- `SECRET_KEY` — long random secret (32+ characters)
- `GROQ_API_KEY` — Groq API key
- `GROQ_MODEL` — optional; default `llama-3.3-70b-versatile`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN` — Workers AI permissions
- `CLOUDFLARE_IMAGE_MODEL` — optional; default `@cf/black-forest-labs/flux-1-schnell`
- `OPENWEATHER_API_KEY`
- `CESIUM_ION_TOKEN` — public restricted Cesium ion Viewer token only; never use an admin/master secret token.

## Important MVP boundaries
- This is a starter, not yet a production-secure public messenger. Add rate limits, account recovery, moderation, origin/CSRF controls and security review before public launch.
- Chat history persists in MongoDB. WebSockets/live delivery, read receipts, push notifications, end-to-end encryption, uploads and detailed group/channel admin controls are not implemented yet.
- Cloudflare image generation returns the image to the browser; image storage/history is not implemented.
- GitHub feature reads public repository metadata only; it does not run or execute arbitrary repository code.
- Cesium displays imagery and attempts ion terrain; access depends on the public viewer token and its scopes. The flight controls/HUD are a prototype, not a physics-accurate flight simulator, and the selected aircraft list is not yet wired to load GLB models into the scene.
- Aircraft choices refer to the public `amvlab/aircraft-models` repository, licensed CC BY 4.0. Verify exact GLB paths and give attribution before wiring actual model files. The 10 options include variants; they are not 10 verified unique model files.
- The pull-down assistant overlay works where the browser delivers the gesture; some mobile operating systems intercept edge swipes. A visible AI button is included as fallback.
- User-entered Cesium token is saved in that browser's localStorage, not in MongoDB; use a public viewer token only.
