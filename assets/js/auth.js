async function getAuthHeaders(includeContentType = false) {
    const headers = {};
    
    if (includeContentType) {
        headers['Content-Type'] = 'application/json';
    }
    
    if (window.Clerk && window.Clerk.session) {
        try {
            const token = await window.Clerk.session.getToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        } catch (err) {
            console.warn('Failed to get Clerk token:', err);
        }
    }
    
    const storedToken = sessionStorage.getItem('clerk_session_token');
    if (!headers['Authorization'] && storedToken) {
        headers['Authorization'] = `Bearer ${storedToken}`;
    }
    
    // Include email header for server-side admin verification
    // (Clerk JWTs don't include email by default)
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
    return sessionStorage.getItem('clerk_session_token');
}

async function authedFetch(url, opts = {}) {
    const authHeaders = await getAuthHeaders(false);
    const mergedHeaders = { ...authHeaders, ...(opts.headers || {}) };
    
    // Auto-set Content-Type for JSON body, but NOT for FormData
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
