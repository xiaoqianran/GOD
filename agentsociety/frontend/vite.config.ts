import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react-swc'

const FRONTEND_PORT = Number(process.env.GOD_FRONTEND_PORT || process.env.VITE_PORT || 5174)

/**
 * ONLY allow a clean base path:
 *   - `/` (local direct access)
 *   - `/proxy/<port>/` (code-server path proxy)
 *
 * Never trust raw VSCODE_PROXY_URI templates: shells/templates can leave
 * stray `}` characters which become %7D in the browser and black-screen the app.
 */
function resolveProxyBase(): string {
    const candidates = [
        process.env.VITE_BASE,
        process.env.VITE_BASE_PATH,
        process.env.VSCODE_PROXY_URI,
    ].filter((v): v is string => Boolean(v && v.trim()))

    for (const raw of candidates) {
        // Nuke braces / encoded braces / whitespace junk entirely.
        const cleaned = raw
            .replace(/%7[Dd]/gi, '')
            .replace(/[{}]/g, '')
            .trim()

        // Already a path like /proxy/5174 or /proxy/5174/
        const pathMatch = cleaned.match(/\/proxy\/(\d+)\/?/)
        if (pathMatch) {
            return `/proxy/${pathMatch[1]}/`
        }

        // Full URL template after brace strip: https://host/proxy/port/
        // or https://host/proxy/{{port}} → https://host/proxy/port after strip of braces
        // becomes https://host/proxy/port  OR  https://host/proxy/  if port token removed
        try {
            if (/^https?:\/\//i.test(cleaned)) {
                const url = new URL(cleaned)
                const m = url.pathname.match(/\/proxy\/(\d+)\/?/)
                if (m) {
                    return `/proxy/${m[1]}/`
                }
                // Template was /proxy/{{port}}/ → braces removed → /proxy// or /proxy/
                if (/\/proxy\/?$/.test(url.pathname) || url.pathname.includes('/proxy')) {
                    return `/proxy/${FRONTEND_PORT}/`
                }
            }
        } catch {
            /* ignore */
        }

        // Plain "/proxy/5174/" style after cleanup
        if (cleaned === '/' || cleaned === '') {
            continue
        }
        if (cleaned.startsWith('/proxy/')) {
            return `/proxy/${FRONTEND_PORT}/`
        }
    }

    // code-server / VS Code tunnel: always use path proxy form.
    if (
        process.env.VSCODE_PROXY_URI ||
        process.env.CODE_SERVER_PARENT_PID ||
        process.env.VSCODE_IPC_HOOK_CLI ||
        process.env.GOD_FORCE_PROXY_BASE === '1'
    ) {
        return `/proxy/${FRONTEND_PORT}/`
    }

    return '/'
}

function resolvePublicOrigin(): string | undefined {
    if (process.env.VITE_DEV_ORIGIN) {
        return process.env.VITE_DEV_ORIGIN.replace(/[}\s]+$/g, '').replace(/\/$/, '')
    }
    const raw = (process.env.VSCODE_PROXY_URI || '').replace(/[{}]/g, '').replace(/%7[Dd]/gi, '')
    if (/^https?:\/\//i.test(raw)) {
        try {
            return new URL(raw).origin
        } catch {
            return undefined
        }
    }
    return undefined
}

/**
 * code-server strips `/proxy/<port>` before talking to Vite, but Vite with a
 * non-root `base` only serves under that base. Re-prefix stripped requests.
 * Leave `/api*` alone so server.proxy still matches.
 */
function codeServerBasePlugin(base: string): Plugin {
    if (base === '/') {
        return { name: 'code-server-base-noop' }
    }
    const prefix = base.endsWith('/') ? base.slice(0, -1) : base
    return {
        name: 'code-server-reprefix-base',
        configureServer(server) {
            // Run first so Vite sees the re-prefixed URL.
            server.middlewares.use((req, _res, next) => {
                let url = req.url || '/'
                const qIndex = url.indexOf('?')
                let path = qIndex >= 0 ? url.slice(0, qIndex) : url
                const query = qIndex >= 0 ? url.slice(qIndex) : ''

                // Broken clients / old caches: /proxy/5174/%7D/%7D/proxy/5174/...
                path = path.replace(/%7[Dd]/gi, '').replace(/[{}]/g, '')
                // Collapse duplicate slashes first so repeated bases are adjacent
                path = path.replace(/\/{2,}/g, '/')
                // Collapse repeated base segments: /proxy/5174/proxy/5174/...
                path = path.replace(new RegExp(`(?:${prefix})+`, 'g'), prefix)
                url = `${path}${query}`
                req.url = url

                if (
                    path === prefix ||
                    path.startsWith(`${prefix}/`) ||
                    path === `${prefix}`
                ) {
                    next()
                    return
                }
                if (path === '/api' || path.startsWith('/api/')) {
                    next()
                    return
                }
                req.url = `${prefix}${path.startsWith('/') ? path : `/${path}`}${query}`
                next()
            })
        },
    }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    loadEnv(mode, process.cwd(), '')
    const base = resolveProxyBase()
    // Always log once so we can diagnose path-proxy issues from frontend.log
    console.log(`[vite] resolved base=${JSON.stringify(base)} port=${FRONTEND_PORT}`)
    const behindProxy = base !== '/'
    const publicOrigin = resolvePublicOrigin()

    return {
        base,
        server: {
            host: process.env.VITE_HOST || '127.0.0.1',
            port: FRONTEND_PORT,
            strictPort: true,
            allowedHosts: true,
            origin: publicOrigin,
            hmr: behindProxy
                ? {
                      protocol: 'wss',
                      clientPort: Number(process.env.VITE_HMR_CLIENT_PORT || 443),
                  }
                : true,
            proxy: {
                '/api/alipay': {
                    target: 'https://agentsociety.fiblab.net',
                    changeOrigin: true,
                },
                '/api/v1': {
                    target: `http://127.0.0.1:${process.env.GOD_BACKEND_PORT || process.env.BACKEND_PORT || 8001}`,
                    changeOrigin: true,
                    ws: true,
                },
                '/api': {
                    target: 'http://127.0.0.1:80',
                    changeOrigin: true,
                },
            },
        },
        plugins: [codeServerBasePlugin(base), react()],
        build: {
            outDir: 'dist',
            assetsDir: 'assets',
            sourcemap: false,
        },
    }
})
