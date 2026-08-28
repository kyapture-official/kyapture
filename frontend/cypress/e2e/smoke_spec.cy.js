// File Location: frontend/cypress/e2e/smoke_spec.cy.js
// VERSION: Gold-Standard Production — Week 12 (Factual Audit Synced)
// Fully resolves selector mismatches, applies C-2 payments routing, and publishes mock collections.

describe('Kyapture Full Platform Integration Smoke Test', () => {
  const uniqueId = Math.random().toString(36).substring(2, 7)
  const username = `photog_${uniqueId}`
  const email = `${username}@test.com`
  const password = 'TestPassword1234!'
  const galleryTitle = `Wedding of Sonal & Lalit ${uniqueId}`

  beforeEach(() => {
    // Standard GET read path intercepts
    cy.intercept('GET', '**/api/v1/auth/me/').as('getMe')
    cy.intercept('GET', '**/api/v1/subscriptions/plans/').as('getPlans')
    cy.intercept('GET', '**/api/v1/subscriptions/my-subscription/').as('getMyPlan')
    cy.intercept('GET', '**/api/v1/subscriptions/payments/').as('getPaymentHistory')

    // BUG RESOLUTION (C-2): Since we successfully verified and aligned the backend route 
    // to /subscriptions/payments/ in Step 2, we intercept this exact path.
    cy.intercept('POST', '**/api/v1/subscriptions/payments/').as('submitPayment')
  })

  // ── 1. PHOTOGRAPHER REGISTRATION ───────────────────────────────────────────
  it('1. Registers a new photographer and initializes session state', () => {
    cy.visit('/register')

    // BUG RESOLUTION: Selectors strictly targeted to match reg- IDs inside RegisterPage.jsx
    cy.get('input[id="reg-display-name"]').type(`Studio ${uniqueId}`)
    cy.get('input[id="reg-username"]').type(username)
    cy.get('input[id="reg-email"]').type(email)
    cy.get('input[id="reg-password"]').type(password)

    // BUG RESOLUTION: Filled the mandatory confirmation field to pass password2 backend verification
    cy.get('input[id="reg-confirm"]').type(password)

    cy.get('button[type="submit"]').click()

    cy.url().should('include', '/dashboard')
    cy.get('h1').should('contain', 'My Collections')
  })

  // ── 2. PORTAL GALLERY CREATION & PUBLIC PUBLISHING ────────────────────────
  it('2. Navigates, spawns the Portal Modal, and creates a gallery', () => {
    cy.visit('/login')
    cy.get('input[id="reg-email"], input[id="email"]').first().type(email)
    cy.get('input[id="reg-password"], input[id="password"]').first().type(password)
    cy.get('button[type="submit"]').click()

    cy.url().should('include', '/dashboard')

    cy.visit('/dashboard/galleries')

    // Resilient regex captures both "New Gallery" and "Create Gallery" variants safely
    cy.get('button').contains(/New Gallery|Create Gallery/i).click()

    // Targets our portal's exact ID selector
    cy.get('input[id="gallery-title"]').type(galleryTitle)
    cy.get('button[type="submit"]').contains(/Create/i).click()

    cy.get('h3').contains(galleryTitle).should('exist')

    // BUG RESOLUTION: Draft collections default to unpublished (is_published = False). 
    // We click the newly created card and trigger "Publish" to enable public client access.
    cy.get('h3').contains(galleryTitle).click()
    cy.get('button').contains('Publish Collection').click()
    cy.get('button').contains('Published').should('exist')
  })

  // ── 3. BILLING UPGRADE & PROOF UPLOAD ──────────────────────────────────────
  it('3. Selects upgrade plan from pricing and submits manual payment slip', () => {
    cy.visit('/login')
    cy.get('input[id="reg-email"], input[id="email"]').first().type(email)
    cy.get('input[id="reg-password"], input[id="password"]').first().type(password)
    cy.get('button[type="submit"]').click()

    cy.visit('/pricing')
    cy.wait('@getPlans')

    cy.get('section').eq(1).within(() => {
      cy.get('button').contains('Upgrade Plan').click()
    })

    cy.url().should('include', '/dashboard/billing?plan_id=')
    cy.wait('@getPaymentHistory')

    cy.get('form').should('contain', 'Upload Proof of Transfer')

    const mockFile = {
      contents: 'fake-image-contents',
      fileName: 'receipt_screenshot.png',
      mimeType: 'image/png',
    }
    cy.get('input[id="manual-receipt-input"]').selectFile(mockFile, { force: true })

    cy.get('textarea').type('Transaction reference ID: ES-1294104')
    cy.get('button[type="submit"]').contains('Submit').click()

    cy.wait('@submitPayment').its('response.statusCode').should('eq', 201)

    cy.get('table').should('contain', 'pending')
  })

  // ── 4. CLIENT PORTAL ACCESS ────────────────────────────────────────────────
  it('4. Visits the public client view and verifies navigation links', () => {
    const slug = galleryTitle.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

    cy.visit(`/g/${username}/${slug}`)

    cy.get('h1').should('contain', galleryTitle)
    cy.get('p').should('contain', `By Studio ${uniqueId}`)
  })
})