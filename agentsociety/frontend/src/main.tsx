import ReactDOM from 'react-dom/client'
import './index.css'
import './i18n'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { ConfigProvider, ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import PixelReplay from './pages/PixelReplay'
import AgentBuilder from './pages/AgentBuilder'

const router = createBrowserRouter([
    {
        path: "/",
        element: <PixelReplay />,
    },
    {
        path: "/pixel-replay",
        element: <PixelReplay />,
    },
    {
        path: "/pixel-replay/:hypothesisId/:experimentId",
        element: <PixelReplay />,
    },
    {
        path: "/agent-builder",
        element: <AgentBuilder />,
    },
    {
        path: "*",
        element: <Navigate to="/" />,
    }
])

const theme: ThemeConfig = {
    token: {
        colorPrimary: "#0000CC",
        colorInfo: "#0000CC",
        borderRadius: 16,
        colorBgContainer: "#FFFFFF",
        colorBgLayout: "#FFFFFF",
    },
    components: {
        Layout: {
            lightSiderBg: "#F8F8F8",
            headerBg: "#FFFFFF",
        },
        Button: {
            algorithm: true,
            colorBgContainer: "#FFFFFF",
        },
        Select: {
            colorBgContainer: "#FFFFFF",
        }
    }
};

const App = () => (
    <ConfigProvider theme={theme} locale={zhCN}>
        <RouterProvider router={router} />
    </ConfigProvider>
)

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
)
