# Headwins Poker frontend

React + TypeScript + Vite. See the [project README](../README.md) for setup, gameplay, tests, and hosting.

```sh
npm ci
npm run dev
npm run lint
npm run build
```

By default, the development server proxies `/ws` to `127.0.0.1:8000`. Use `.env.development.local` to override `VITE_WS_URL`; `.env.example` documents the setting.
