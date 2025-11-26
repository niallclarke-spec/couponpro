# EntryLab Telegram Subscription API Integration

## Overview
This document describes the API endpoints for integrating EntryLab's subscription system with PromoStack's Telegram private channel access control.

## Base URL
- **Development**: `https://your-replit-dev-url.repl.co`
- **Production**: `https://dash.promostack.io`

## Authentication
All API endpoints require an API key for authentication.

### Header Options
1. **Recommended**: `X-API-Key: your_api_key_here`
2. **Alternative**: `Authorization: Bearer your_api_key_here`

### Environment Variable
The API key must be configured in both systems:
- **PromoStack**: `ENTRYLAB_API_KEY` secret
- **EntryLab**: Same value stored securely

## API Endpoints

---

### 1. Grant Access (Create Subscription)

Creates a new subscription and generates a private Telegram channel invite link.

**Endpoint**: `POST /api/telegram/grant-access`

**Headers**:
```
X-API-Key: your_api_key_here
Content-Type: application/json
```

**Request Body**:
```json
{
  "email": "customer@example.com",
  "name": "John Doe",
  "plan_type": "Premium Forex Signals",
  "amount_paid": 49,
  "stripe_customer_id": "cus_xxxxxxxxxxxxx",
  "stripe_subscription_id": "sub_xxxxxxxxxxxxx"
}
```

**Success Response** (200):
```json
{
  "success": true,
  "inviteLink": "https://t.me/+AbCdEfGhIjKlMnO",
  "message": "Access granted successfully"
}
```

**Error Responses**:
- `400`: Missing required fields or subscription already exists
- `401`: Unauthorized - Invalid API key
- `500`: Server error creating subscription

**Example (Node.js)**:
```javascript
const response = await fetch('https://dash.promostack.io/api/telegram/grant-access', {
  method: 'POST',
  headers: {
    'X-API-Key': process.env.PROMOSTACK_API_KEY,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    email: 'customer@example.com',
    name: 'John Doe',
    plan_type: 'Premium Forex Signals',
    amount_paid: 49,
    stripe_customer_id: 'cus_xxxxxxxxxxxxx',
    stripe_subscription_id: 'sub_xxxxxxxxxxxxx'
  })
});

const data = await response.json();
console.log('Invite link:', data.inviteLink);
```

**Example (cURL)**:
```bash
curl -X POST https://dash.promostack.io/api/telegram/grant-access \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "name": "John Doe",
    "plan_type": "Premium Forex Signals",
    "amount_paid": 49,
    "stripe_customer_id": "cus_xxxxxxxxxxxxx",
    "stripe_subscription_id": "sub_xxxxxxxxxxxxx"
  }'
```

---

### 2. Revoke Access (Cancel Subscription)

Revokes access by kicking the user from the private channel and updating subscription status.

**Endpoint**: `POST /api/telegram/revoke-access`

**Headers**:
```
X-API-Key: your_api_key_here
Content-Type: application/json
```

**Request Body**:
```json
{
  "email": "customer@example.com",
  "reason": "subscription_cancelled"
}
```

**Success Response** (200):
```json
{
  "success": true,
  "message": "Access revoked successfully"
}
```

**Error Responses**:
- `400`: Missing email parameter
- `401`: Unauthorized - Invalid API key
- `404`: Subscription not found
- `500`: Server error revoking access

**Example (Node.js)**:
```javascript
const response = await fetch('https://dash.promostack.io/api/telegram/revoke-access', {
  method: 'POST',
  headers: {
    'X-API-Key': process.env.PROMOSTACK_API_KEY,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    email: 'customer@example.com',
    reason: 'subscription_cancelled'
  })
});

const data = await response.json();
console.log(data.message);
```

---

### 3. Check Access Status

Retrieves subscription status and access information for a customer.

**Endpoint**: `GET /api/telegram/check-access/:email`

**Headers**:
```
X-API-Key: your_api_key_here
```

**URL Parameters**:
- `:email` - Customer email (URL-encoded)

**Success Response** (200):
```json
{
  "hasAccess": true,
  "telegramUserId": "123456789",
  "telegramUsername": "@johndoe",
  "status": "active",
  "joinedAt": "2025-11-26T10:30:00Z",
  "lastSeenAt": "2025-11-26T15:45:00Z"
}
```

**No Access Response** (200):
```json
{
  "hasAccess": false,
  "error": "No subscription found for customer@example.com"
}
```

**Error Responses**:
- `400`: Missing email parameter
- `401`: Unauthorized - Invalid API key
- `500`: Server error checking access

**Example (Node.js)**:
```javascript
const email = encodeURIComponent('customer@example.com');
const response = await fetch(`https://dash.promostack.io/api/telegram/check-access/${email}`, {
  headers: {
    'X-API-Key': process.env.PROMOSTACK_API_KEY
  }
});

const data = await response.json();
console.log('Has access:', data.hasAccess);
console.log('Status:', data.status);
```

**Example (cURL)**:
```bash
curl -X GET "https://dash.promostack.io/api/telegram/check-access/customer%40example.com" \
  -H "X-API-Key: your_api_key_here"
```

---

## Integration Workflow

### New Subscription Flow
1. Customer completes payment on EntryLab
2. EntryLab calls `POST /api/telegram/grant-access` with customer details
3. PromoStack creates subscription record and generates invite link
4. EntryLab receives invite link and displays it to customer
5. Customer clicks link and joins private Telegram channel
6. PromoStack auto-tracks join (updates `telegram_user_id`, `joined_at`, `last_seen_at`)

### Cancellation Flow
1. Customer cancels subscription on EntryLab (or payment fails)
2. EntryLab calls `POST /api/telegram/revoke-access` with customer email
3. PromoStack kicks user from channel and marks subscription as revoked
4. Customer loses access to private channel signals

### Status Check Flow
1. EntryLab needs to verify subscription status
2. EntryLab calls `GET /api/telegram/check-access/:email`
3. PromoStack returns current access status and Telegram details

---

## Subscription Statuses

| Status | Description |
|--------|-------------|
| `pending` | Subscription created but user hasn't joined Telegram yet |
| `active` | User has joined and has active access |
| `revoked` | Access has been revoked (cancelled, payment failed, etc.) |

---

## Database Schema (Reference)

```sql
CREATE TABLE telegram_subscriptions (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    telegram_user_id BIGINT,
    telegram_username VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    plan_type VARCHAR(100),
    amount_paid DECIMAL(10,2),
    status VARCHAR(50) DEFAULT 'pending',
    invite_link TEXT,
    joined_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Error Handling Best Practices

### 1. Always Check Response Status
```javascript
const response = await fetch(url, options);
if (!response.ok) {
  const error = await response.json();
  console.error('API Error:', error);
  // Handle error appropriately
}
```

### 2. Handle Network Failures
```javascript
try {
  const response = await fetch(url, options);
  const data = await response.json();
  // Process data
} catch (error) {
  console.error('Network error:', error);
  // Retry or notify user
}
```

### 3. Validate Invite Links Before Display
```javascript
if (data.success && data.inviteLink && data.inviteLink.startsWith('https://t.me/')) {
  // Display invite link to user
} else {
  // Handle invalid response
}
```

---

## Security Considerations

1. **API Key Storage**: Never commit API keys to version control. Use environment variables.
2. **HTTPS Only**: All API calls must use HTTPS in production.
3. **Email Validation**: Validate email format before making API calls.
4. **Rate Limiting**: Implement exponential backoff for retries.
5. **Logging**: Log API calls (excluding API keys) for debugging and audit trails.

---

## Testing

### Development Environment
Use the development API key and development base URL for testing:
```javascript
const BASE_URL = 'https://your-replit-dev-url.repl.co';
const API_KEY = process.env.PROMOSTACK_API_KEY_DEV;
```

### Test Flow
1. Create test subscription with `POST /api/telegram/grant-access`
2. Verify invite link is generated
3. Check status with `GET /api/telegram/check-access/:email`
4. Revoke access with `POST /api/telegram/revoke-access`
5. Verify status changed to `revoked`

---

## Support

For issues or questions about the API integration:
- **Admin Dashboard**: https://admin.promostack.io/admin-telegram-subscriptions.html
- **API Status**: Monitor via admin dashboard
- **Logs**: Check PromoStack server logs for detailed error messages

---

## Changelog

### 2025-11-26
- Initial API release
- Added grant-access, revoke-access, and check-access endpoints
- Implemented API key authentication
- Created admin dashboard for subscription management
