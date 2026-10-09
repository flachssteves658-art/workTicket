import { defineConfig, loadEnv } from 'vite';

function pickTarget(value, fallback) {
  const v = typeof value === 'string' ? value.trim() : '';
  return v || fallback;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  const streamingTarget = pickTarget(
    env.VITE_STREAMING_BACKEND_API_URL,
    'http://127.0.0.1:8800',
  );
  const platformTarget = pickTarget(
    env.VITE_PLATFORM_API_URL,
    'http://127.0.0.1:8005',
  );
  const violationTarget = pickTarget(
    env.VITE_VIOLATION_API_URL,
    'http://127.0.0.1:8002',
  );

  return {
    root: 'public',
    publicDir: 'static',
    server: {
      port: 8888,
      proxy: {
        '/api/streaming': {
          target: streamingTarget,
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/api\/streaming/, ''),
        },
        '/api/platform': {
          target: platformTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/platform/, ''),
        },
        '/api/violation': {
          target: violationTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/violation/, ''),
        },
        '/api': {
          target: streamingTarget,
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
    build: {
      outDir: '../dist',
      rollupOptions: {
        input: {
          main: './public/index.html',
          label: './public/label.html',
          camera: './public/camera.html',
          config: './public/config.html',
          violations: './public/violations.html',
          sites: './public/sites.html',
        },
      },
    },
  };
});
