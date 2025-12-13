function getClerkToken() {
    return sessionStorage.getItem('clerk_session_token');
}

async function authedFetch(url, opts = {}) {
    const token = getClerkToken();
    const headers = { ...(opts.headers || {}) };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return fetch(url, { ...opts, headers });
}
