let _clerkReady = false;
let _clerkReadyPromise = null;
let _clerkReadyResolve = null;

(function() {
    _clerkReadyPromise = new Promise(resolve => {
        _clerkReadyResolve = resolve;
    });
})();

async function initClerkOnPage() {
    if (window.Clerk && _clerkReady) return;

    try {
        const resp = await fetch('/api/config');
        if (!resp.ok) return;
        const config = await resp.json();
        const key = config.clerkPublishableKey;
        if (!key) return;

        if (!window.Clerk) {
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
                script.crossOrigin = 'anonymous';
                script.setAttribute('data-clerk-publishable-key', key);
                script.onload = () => {
                    const check = setInterval(() => {
                        if (window.Clerk) {
                            clearInterval(check);
                            resolve();
                        }
                    }, 50);
                    setTimeout(() => {
                        clearInterval(check);
                        if (!window.Clerk) reject(new Error('Clerk init timeout'));
                    }, 8000);
                };
                script.onerror = () => reject(new Error('Clerk script failed'));
                document.head.appendChild(script);
            });
        }

        await window.Clerk.load();
        _clerkReady = true;
        if (_clerkReadyResolve) _clerkReadyResolve();
    } catch (err) {
        console.warn('[Auth] Clerk init failed, using cookie auth:', err.message);
        if (_clerkReadyResolve) _clerkReadyResolve();
    }
}

function isClerkAvailable() {
    return _clerkReady && window.Clerk && window.Clerk.session;
}

async function getAuthHeaders(includeContentType = false) {
    const headers = {};

    if (includeContentType) {
        headers['Content-Type'] = 'application/json';
    }

    if (isClerkAvailable()) {
        try {
            const token = await window.Clerk.session.getToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        } catch (err) {
            console.warn('[Auth] getToken failed:', err.message);
        }
    }

    let userEmail = sessionStorage.getItem('clerk_user_email');
    if (window.Clerk && window.Clerk.user) {
        userEmail = window.Clerk.user.primaryEmailAddress?.emailAddress ||
                    window.Clerk.user.emailAddresses?.[0]?.emailAddress ||
                    userEmail;
    }
    if (userEmail) {
        headers['X-Clerk-User-Email'] = userEmail;
    }

    return headers;
}

function getClerkToken() {
    return null;
}

async function authedFetch(url, opts = {}) {
    const authHeaders = await getAuthHeaders(false);
    const mergedHeaders = { ...authHeaders, ...(opts.headers || {}) };

    if (opts.body && typeof opts.body === 'string' && !mergedHeaders['Content-Type']) {
        mergedHeaders['Content-Type'] = 'application/json';
    }

    return fetch(url, { ...opts, headers: mergedHeaders, credentials: 'include' });
}

async function authedJsonFetch(url, opts = {}) {
    const authHeaders = await getAuthHeaders(true);
    const mergedHeaders = { ...authHeaders, ...(opts.headers || {}) };
    return fetch(url, { ...opts, headers: mergedHeaders, credentials: 'include' });
}
