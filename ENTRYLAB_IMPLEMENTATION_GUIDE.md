# EntryLab Implementation Guide: Telegram Subscription Integration

## 🎯 Overview
This guide will help you integrate EntryLab's payment system with PromoStack's Telegram channel access control. After a customer subscribes via Stripe, you'll grant them access to the private forex signals Telegram channel.

---

## 🔑 API Credentials

### **PromoStack API Key**
```
PROMOSTACK_API_KEY=3JPi0yAu6gWrG919ufhZrEh5zfkA2Hiz9_zZlAsmy2o
```

**Important:** Store this as an environment variable in your EntryLab project. Never commit it to version control.

### **API Base URLs**
```
Development: https://your-promostack-dev-url.repl.co
Production:  https://dash.promostack.io
```

---

## 📋 Implementation Checklist

### **Phase 1: Stripe Webhook Handler**
- [ ] Set up Stripe webhook endpoint
- [ ] Handle `checkout.session.completed` event
- [ ] Extract customer email, name, and subscription details
- [ ] Call PromoStack grant-access API
- [ ] Send welcome email with invite link

### **Phase 2: Subscription Management**
- [ ] Handle `customer.subscription.deleted` event
- [ ] Call PromoStack revoke-access API
- [ ] Send cancellation email

### **Phase 3: Email Templates (Resend)**
- [ ] Sign up for Resend account
- [ ] Verify your domain (e.g., entrylab.io)
- [ ] Create welcome email template
- [ ] Create cancellation email template
- [ ] Test email delivery

### **Phase 4: Testing**
- [ ] Test successful subscription flow
- [ ] Test cancellation flow
- [ ] Verify Telegram invite links work
- [ ] Confirm user receives emails

---

## 🚀 Step-by-Step Implementation

### **Step 1: Install Dependencies**

```bash
npm install stripe resend
# or
yarn add stripe resend
```

### **Step 2: Environment Variables**

Add these to your `.env` file:

```env
# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# PromoStack API
PROMOSTACK_API_URL=https://dash.promostack.io
PROMOSTACK_API_KEY=3JPi0yAu6gWrG919ufhZrEh5zfkA2Hiz9_zZlAsmy2o

# Resend
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@entrylab.io
```

---

### **Step 3: Create PromoStack API Client**

Create `lib/promostack.js`:

```javascript
const PROMOSTACK_API_URL = process.env.PROMOSTACK_API_URL;
const PROMOSTACK_API_KEY = process.env.PROMOSTACK_API_KEY;

/**
 * Grant Telegram channel access to a subscriber
 * @param {Object} params - Subscription details
 * @returns {Promise<{success: boolean, inviteLink: string}>}
 */
export async function grantTelegramAccess(params) {
  const { email, name, planType, amountPaid, stripeCustomerId, stripeSubscriptionId } = params;
  
  try {
    const response = await fetch(`${PROMOSTACK_API_URL}/api/telegram/grant-access`, {
      method: 'POST',
      headers: {
        'X-API-Key': PROMOSTACK_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        email,
        name,
        planType,
        amountPaid,
        stripeCustomerId,
        stripeSubscriptionId
      })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(`PromoStack API error: ${error.error}`);
    }
    
    const data = await response.json();
    return data; // { success: true, inviteLink: "https://t.me/+..." }
    
  } catch (error) {
    console.error('Failed to grant Telegram access:', error);
    throw error;
  }
}

/**
 * Revoke Telegram channel access from a subscriber
 * @param {string} email - Customer email
 * @param {string} reason - Cancellation reason
 * @returns {Promise<{success: boolean}>}
 */
export async function revokeTelegramAccess(email, reason = 'subscription_cancelled') {
  try {
    const response = await fetch(`${PROMOSTACK_API_URL}/api/telegram/revoke-access`, {
      method: 'POST',
      headers: {
        'X-API-Key': PROMOSTACK_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email, reason })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(`PromoStack API error: ${error.error}`);
    }
    
    return await response.json(); // { success: true }
    
  } catch (error) {
    console.error('Failed to revoke Telegram access:', error);
    throw error;
  }
}

/**
 * Check Telegram channel access status for a subscriber
 * @param {string} email - Customer email
 * @returns {Promise<Object>} Access status details
 */
export async function checkTelegramAccess(email) {
  try {
    const encodedEmail = encodeURIComponent(email);
    const response = await fetch(
      `${PROMOSTACK_API_URL}/api/telegram/check-access/${encodedEmail}`,
      {
        headers: {
          'X-API-Key': PROMOSTACK_API_KEY
        }
      }
    );
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(`PromoStack API error: ${error.error}`);
    }
    
    return await response.json();
    // {
    //   hasAccess: true/false,
    //   telegramUserId: "123456789",
    //   telegramUsername: "@johndoe",
    //   status: "active",
    //   joinedAt: "2025-11-26T10:30:00Z",
    //   lastSeenAt: "2025-11-26T15:45:00Z"
    // }
    
  } catch (error) {
    console.error('Failed to check Telegram access:', error);
    throw error;
  }
}
```

---

### **Step 4: Set Up Resend Email Service**

Create `lib/email.js`:

```javascript
import { Resend } from 'resend';

const resend = new Resend(process.env.RESEND_API_KEY);
const FROM_EMAIL = process.env.RESEND_FROM_EMAIL || 'noreply@entrylab.io';

/**
 * Send welcome email with Telegram invite link
 */
export async function sendWelcomeEmail(email, name, inviteLink) {
  try {
    const data = await resend.emails.send({
      from: `EntryLab <${FROM_EMAIL}>`,
      to: email,
      subject: 'Welcome to EntryLab Premium Forex Signals! 🎯',
      html: `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }
            .content { background: #f9f9f9; padding: 40px 20px; border-radius: 0 0 8px 8px; }
            .cta-button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white !important; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; }
            .footer { text-align: center; padding: 20px; color: #666; font-size: 14px; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>🎉 Welcome to EntryLab!</h1>
              <p>Your premium forex signals subscription is now active</p>
            </div>
            <div class="content">
              <p>Hi ${name || 'there'},</p>
              
              <p>Thank you for subscribing to EntryLab Premium Forex Signals! You now have exclusive access to our private Telegram channel where you'll receive:</p>
              
              <ul>
                <li>🎯 Real-time XAU/USD (Gold) trading signals</li>
                <li>📊 Multi-indicator technical analysis</li>
                <li>💰 Clear entry, take profit, and stop loss levels</li>
                <li>📈 Daily and weekly performance recaps</li>
                <li>🏆 AI-powered celebration messages on winning trades</li>
              </ul>
              
              <p><strong>Next Step: Join the Private Telegram Channel</strong></p>
              
              <p>Click the button below to join our exclusive forex signals channel:</p>
              
              <a href="${inviteLink}" class="cta-button">Join Telegram Channel →</a>
              
              <p style="font-size: 14px; color: #666;">
                <strong>Important:</strong> This invite link is unique to your account and can only be used once. 
                Keep it secure and do not share it with others.
              </p>
              
              <p>Once you join, you'll start receiving signals immediately during market hours (8 AM - 10 PM GMT).</p>
              
              <p>If you have any questions, feel free to reply to this email.</p>
              
              <p>Happy trading! 📊</p>
              <p><strong>The EntryLab Team</strong></p>
            </div>
            <div class="footer">
              <p>© 2025 EntryLab. All rights reserved.</p>
              <p>You're receiving this because you subscribed to EntryLab Premium Forex Signals.</p>
            </div>
          </div>
        </body>
        </html>
      `
    });
    
    console.log('Welcome email sent:', data);
    return data;
    
  } catch (error) {
    console.error('Failed to send welcome email:', error);
    throw error;
  }
}

/**
 * Send cancellation email
 */
export async function sendCancellationEmail(email, name) {
  try {
    const data = await resend.emails.send({
      from: `EntryLab <${FROM_EMAIL}>`,
      to: email,
      subject: 'Your EntryLab Subscription Has Been Cancelled',
      html: `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: #f5f5f5; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }
            .content { background: #fafafa; padding: 40px 20px; border-radius: 0 0 8px 8px; }
            .cta-button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white !important; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; }
            .footer { text-align: center; padding: 20px; color: #666; font-size: 14px; }
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>Subscription Cancelled</h1>
            </div>
            <div class="content">
              <p>Hi ${name || 'there'},</p>
              
              <p>We're sorry to see you go! Your EntryLab Premium Forex Signals subscription has been cancelled, and your access to the private Telegram channel has been removed.</p>
              
              <p><strong>What happens next:</strong></p>
              
              <ul>
                <li>You will no longer receive forex signals in Telegram</li>
                <li>Your subscription will not renew</li>
                <li>No further charges will be made</li>
              </ul>
              
              <p>If you change your mind, you can resubscribe anytime:</p>
              
              <a href="https://entrylab.io/pricing" class="cta-button">Resubscribe Now →</a>
              
              <p>We'd love to hear your feedback! Reply to this email and let us know how we can improve.</p>
              
              <p>Thank you for being part of EntryLab.</p>
              <p><strong>The EntryLab Team</strong></p>
            </div>
            <div class="footer">
              <p>© 2025 EntryLab. All rights reserved.</p>
            </div>
          </div>
        </body>
        </html>
      `
    });
    
    console.log('Cancellation email sent:', data);
    return data;
    
  } catch (error) {
    console.error('Failed to send cancellation email:', error);
    throw error;
  }
}
```

---

### **Step 5: Stripe Webhook Handler**

Create `pages/api/webhooks/stripe.js` (Next.js example):

```javascript
import Stripe from 'stripe';
import { grantTelegramAccess, revokeTelegramAccess } from '../../../lib/promostack';
import { sendWelcomeEmail, sendCancellationEmail } from '../../../lib/email';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

export const config = {
  api: {
    bodyParser: false, // Disable body parsing, need raw body for signature verification
  },
};

async function buffer(readable) {
  const chunks = [];
  for await (const chunk of readable) {
    chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const buf = await buffer(req);
  const sig = req.headers['stripe-signature'];

  let event;

  try {
    event = stripe.webhooks.constructEvent(buf, sig, webhookSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).json({ error: `Webhook Error: ${err.message}` });
  }

  console.log('Received Stripe event:', event.type);

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        
        // Extract customer details
        const customerEmail = session.customer_details?.email || session.customer_email;
        const customerName = session.customer_details?.name;
        const stripeCustomerId = session.customer;
        const stripeSubscriptionId = session.subscription;
        const amountPaid = session.amount_total / 100; // Convert cents to dollars
        
        console.log('New subscription:', { customerEmail, customerName, amountPaid });
        
        // Grant Telegram access
        const { inviteLink } = await grantTelegramAccess({
          email: customerEmail,
          name: customerName,
          planType: 'Premium Forex Signals',
          amountPaid,
          stripeCustomerId,
          stripeSubscriptionId
        });
        
        console.log('Telegram access granted, invite link:', inviteLink);
        
        // Send welcome email with invite link
        await sendWelcomeEmail(customerEmail, customerName, inviteLink);
        
        console.log('Welcome email sent to:', customerEmail);
        break;
      }
      
      case 'customer.subscription.deleted': {
        const subscription = event.data.object;
        
        // Get customer email from Stripe
        const customer = await stripe.customers.retrieve(subscription.customer);
        const customerEmail = customer.email;
        
        console.log('Subscription cancelled:', customerEmail);
        
        // Revoke Telegram access
        await revokeTelegramAccess(customerEmail, 'subscription_cancelled');
        
        console.log('Telegram access revoked for:', customerEmail);
        
        // Send cancellation email
        await sendCancellationEmail(customerEmail, customer.name);
        
        console.log('Cancellation email sent to:', customerEmail);
        break;
      }
      
      case 'invoice.payment_failed': {
        const invoice = event.data.object;
        
        // Get customer email
        const customer = await stripe.customers.retrieve(invoice.customer);
        const customerEmail = customer.email;
        
        console.log('Payment failed for:', customerEmail);
        
        // Optionally: Send payment failed warning email
        // You can add a grace period before revoking access
        
        break;
      }
      
      default:
        console.log(`Unhandled event type: ${event.type}`);
    }
    
    res.status(200).json({ received: true });
    
  } catch (error) {
    console.error('Error processing webhook:', error);
    res.status(500).json({ error: 'Webhook processing failed' });
  }
}
```

---

### **Step 6: User Dashboard (Optional)**

Add Telegram status to customer dashboard:

```javascript
import { checkTelegramAccess } from '../lib/promostack';

export default async function Dashboard({ user }) {
  const telegramStatus = await checkTelegramAccess(user.email);
  
  return (
    <div>
      <h1>Dashboard</h1>
      
      <div className="telegram-status">
        {telegramStatus.hasAccess ? (
          <div className="success">
            ✅ Connected to Telegram as @{telegramStatus.telegramUsername}
            <p>Last active: {new Date(telegramStatus.lastSeenAt).toLocaleString()}</p>
          </div>
        ) : telegramStatus.status === 'active' ? (
          <div className="warning">
            ⏸️ Subscription active, but you haven't joined Telegram yet.
            <p>Check your email for the invite link!</p>
          </div>
        ) : (
          <div className="error">
            ❌ No active subscription
          </div>
        )}
      </div>
    </div>
  );
}
```

---

## 🧪 Testing Guide

### **Test Successful Subscription:**

1. Create a test Stripe checkout session
2. Complete payment using test card: `4242 4242 4242 4242`
3. Verify webhook is received
4. Check console logs for:
   - ✅ "Telegram access granted"
   - ✅ "Welcome email sent"
5. Check email inbox for welcome email with invite link
6. Click invite link and join Telegram channel
7. Verify you receive forex signals

### **Test Cancellation:**

1. Cancel subscription in Stripe Dashboard
2. Verify webhook is received
3. Check console logs for:
   - ✅ "Telegram access revoked"
   - ✅ "Cancellation email sent"
4. Verify you're kicked from Telegram channel
5. Check email inbox for cancellation email

---

## 🐛 Troubleshooting

### **Issue: "Unauthorized - Invalid API key"**
- Verify `PROMOSTACK_API_KEY` is set correctly
- Check you're using the correct header: `X-API-Key`

### **Issue: "Failed to create invite link"**
- Verify @entrylab_bot has admin permissions in Telegram channel
- Check bot can "Add Subscribers" (enabled in channel admin settings)

### **Issue: "No subscription found"**
- Email might be case-sensitive
- Check exact email used in Stripe matches PromoStack API call

### **Issue: Emails not sending**
- Verify domain in Resend dashboard
- Check DNS records (SPF, DKIM) are configured
- Use Resend test mode for development

---

## 📊 Monitoring & Analytics

### **Track These Metrics:**

1. **Conversion Rate:** Subscriptions → Telegram Joins
2. **Time to Join:** Payment → First Telegram activity
3. **Churn Rate:** Cancellations per month
4. **Email Open Rates:** Welcome email performance

### **PromoStack Admin Dashboard:**

Access the subscription admin panel:
```
https://admin.promostack.io/admin-telegram-subscriptions.html
```

Features:
- View all subscribers
- Search & filter by status
- Manual access revocation
- Telegram activity tracking

---

## 🚀 Go Live Checklist

- [ ] Stripe webhook endpoint deployed and verified
- [ ] Environment variables set in production
- [ ] Resend domain verified and DNS configured
- [ ] PromoStack API credentials secured
- [ ] Email templates tested and approved
- [ ] Test subscription flow end-to-end
- [ ] Monitor logs for first 24 hours
- [ ] Set up error alerting (Sentry, etc.)

---

## 📞 Support

**PromoStack API Issues:**
- Admin Dashboard: https://admin.promostack.io/admin-telegram-subscriptions.html
- Check server logs for detailed error messages

**Resend Email Issues:**
- Dashboard: https://resend.com/dashboard
- Check email delivery logs

**Stripe Webhook Issues:**
- Dashboard: https://dashboard.stripe.com/webhooks
- Test webhooks with Stripe CLI: `stripe trigger checkout.session.completed`

---

## ✅ Next Steps

1. **Install dependencies** (`stripe`, `resend`)
2. **Set environment variables** (API keys)
3. **Copy code files** (promostack.js, email.js, webhook handler)
4. **Set up Resend account** and verify domain
5. **Configure Stripe webhook** endpoint
6. **Test full flow** with test cards
7. **Deploy to production** 🚀

Good luck! 🎯
