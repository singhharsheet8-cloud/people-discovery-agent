# E2E Tests - People Discovery Platform

Comprehensive end-to-end tests for the People Discovery Platform with screenshots at each step.

## Prerequisites

- Node.js 18+
- npm or pnpm

## Setup

```bash
cd frontend
npm install
npx playwright install chromium
```

## Run Tests

Tests run against **https://frontend-theta-seven-44.vercel.app** by default.

```bash
npm run test:e2e
```

To test a different deployment:

```bash
E2E_BASE_URL=https://your-deployment.vercel.app npm run test:e2e
```

## Screenshots

Screenshots are saved to `frontend/e2e-screenshots/` after each test step:

| File | Step |
|------|------|
| 01-login-page.png | Login page before credentials |
| 02-after-login.png | Admin dashboard after successful login |
| 03-persons-list.png | Discovered persons table |
| 04-persons-search-elon.png | Filtered results for "Elon" |
| 05-person-detail.png | Elon Musk profile detail page |
| 06-cost-dashboard.png | Cost Dashboard with stats |
| 07-api-keys-page.png | API Key Management page |
| 08-api-key-created.png | After creating "Test Key" |
| 09-webhooks-page.png | Webhook Management page |
| 10-compare-page.png | Compare page (empty) |
| 11-compare-suggestions.png | Compare with "Sam" suggestions |
| 12-compare-result.png | Sam Altman vs Jensen Huang comparison |
| 13-api-docs.png | API Documentation page |
| 14-api-docs-expanded.png | API docs with endpoint expanded |
| 15-after-logout.png | Login page after logout |

## Test Coverage

1. **Login** - Form validation, credentials, redirect to /admin
2. **Admin Persons** - Table data, search filter
3. **Person Detail** - Profile data, Export buttons (JSON/CSV/PDF), Re-search
4. **Cost Dashboard** - Total Spend, Total Jobs, Avg Cost, recent jobs
5. **API Keys** - Page load, create new key "Test Key"
6. **Webhooks** - Page load, event checkboxes
7. **Compare** - Person A/B search, suggestions, comparison view
8. **API Docs** - Base URL, endpoint sections, expand endpoint
9. **Logout** - Redirect to login

## View Report

```bash
npm run test:e2e:report
```

## UI Mode (Debug)

```bash
npm run test:e2e:ui
```
