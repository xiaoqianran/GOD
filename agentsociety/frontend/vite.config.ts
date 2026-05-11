import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig({
    server: {
        proxy: {
            '/api/alipay': {
                target: 'https://agentsociety.fiblab.net',
                changeOrigin: true,
            },
            '/api/v1': {
                target: 'http://localhost:8001',
                changeOrigin: true,
                ws: true,
            },
            '/api': {
                target: 'http://localhost:80',
                changeOrigin: true,
            }
        }
    },
    plugins: [react()],
    base: '/',
    build: {
        outDir: 'dist',
        assetsDir: 'assets',
        sourcemap: false,
    }
})
