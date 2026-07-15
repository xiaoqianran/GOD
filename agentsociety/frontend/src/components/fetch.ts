import { t } from "i18next";
import { getAccessToken } from "./Auth";
import { message } from "antd";

export const WITH_AUTH = import.meta.env.VITE_WITH_AUTH === 'true';

/**
 * When the UI is served under a path proxy (code-server: /proxy/5174/),
 * absolute /api/... calls would hit the site root and miss Vite's proxy.
 * Prefix same-origin API paths with import.meta.env.BASE_URL.
 */
export const resolveAppUrl = (url: string): string => {
    if (!url || /^https?:\/\//i.test(url) || url.startsWith('//')) {
        return url;
    }
    const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
    if (!base || base === '') {
        return url;
    }
    if (url.startsWith('/api') || url.startsWith('/file-api')) {
        return `${base}${url}`;
    }
    return url;
};

export const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const token = getAccessToken();
    if (!token) {
        throw new Error("No token found, please login");
    }
    options.headers = { ...options.headers, Authorization: `Bearer ${token}` };
    return fetch(resolveAppUrl(url), options);
}

export const fetchCustom = async (url: string, options: RequestInit = {}) => {
    if (WITH_AUTH) {
        return fetchWithAuth(url, options);
    }
    return fetch(resolveAppUrl(url), options);
};

export const postDownload = async (url: string) => {
    const form = document.createElement('form');
    form.action = url;
    form.method = 'POST';
    form.target = '_blank';
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
}

export const postDownloadWithAuth = async (url: string) => {
    const token = getAccessToken();
    if (!token) {
        message.error(t('console.messages.noToken'));
        return;
    }
    const authorization = `Bearer ${token}`;
    const form = document.createElement('form');
    form.action = url;
    form.method = 'POST';
    form.target = '_blank';
    form.innerHTML = '<input type="hidden" name="authorization" value="' + authorization + '">';
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
}

export const postDownloadCustom = async (url: string) => {
    if (WITH_AUTH) {
        return postDownloadWithAuth(url);
    }
    return postDownload(url);
}
