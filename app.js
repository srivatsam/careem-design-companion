/**
 * Design Companion AI - Main Application Script
 * A premium AI design companion for brainstorming layouts, UI copy, and usability feedback.
 */

// --- 1. Static Chat Data (CONVERSATIONS object) ---
const CONVERSATIONS = {
  'layout-brainstorm': {
    id: 'layout-brainstorm',
    title: 'Layout Brainstorming',
    modeIcon: '🎨',
    color: '#28BB4E', // careem green
    preview: 'Dashboard layout recommendations for SaaS',
    messages: [
      { sender: 'user', text: "I'm designing a dashboard for our analytics SaaS product. We need to show KPIs, charts, and a data table. What layout would you recommend?", timestamp: '10:00 AM' },
      { sender: 'ai', text: `I can help with that. Here are 3 layout recommendations for an analytics SaaS dashboard:\n\n` + 
        `<div class="layout-cards">\n` +
        `  <div class="layout-card">\n` +
        `    <div class="layout-viz z-pattern">\n` +
        `      <div class="kpi-row"><div class="box"></div><div class="box"></div><div class="box"></div><div class="box"></div></div>\n` +
        `      <div class="chart-row"><div class="box main-chart"></div><div class="box side-chart"></div></div>\n` +
        `      <div class="table-row"><div class="box full-table"></div></div>\n` +
        `    </div>\n` +
        `    <div class="layout-details">\n` +
        `      <h3>Z-Pattern Dashboard</h3>\n` +
        `      <p>KPI cards across top → main chart center-left → secondary charts right → data table bottom. Uses the natural Z-reading pattern.</p>\n` +
        `      <div class="pros-cons"><div><span class="pro-icon">✓</span> Highly scannable</div><div><span class="con-icon">✕</span> Can feel rigid</div></div>\n` +
        `      <div class="best-for"><strong>Best for:</strong> Standard executive dashboards</div>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="layout-card">\n` +
        `    <div class="layout-viz bento-grid">\n` +
        `      <div class="box hero"></div>\n` +
        `      <div class="box small1"></div><div class="box small2"></div>\n` +
        `      <div class="box medium1"></div><div class="box medium2"></div>\n` +
        `    </div>\n` +
        `    <div class="layout-details">\n` +
        `      <h3>Bento Grid Layout</h3>\n` +
        `      <p>Asymmetric grid with varied card sizes. Large hero metric, medium charts, small KPI tiles. Modern and visually dynamic.</p>\n` +
        `      <div class="pros-cons"><div><span class="pro-icon">✓</span> Engaging, flexible</div><div><span class="con-icon">✕</span> Harder to make responsive</div></div>\n` +
        `      <div class="best-for"><strong>Best for:</strong> Modern SaaS analytics</div>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="layout-card">\n` +
        `    <div class="layout-viz command-center">\n` +
        `      <div class="box top-nav"></div>\n` +
        `      <div class="split-view"><div class="box sidebar"></div><div class="box main-content"></div></div>\n` +
        `    </div>\n` +
        `    <div class="layout-details">\n` +
        `      <h3>Command Center</h3>\n` +
        `      <p>Full-width top nav → split view with sidebar filters + main content area with tabbed sections.</p>\n` +
        `      <div class="pros-cons"><div><span class="pro-icon">✓</span> Handles complex controls</div><div><span class="con-icon">✕</span> Can feel overwhelming</div></div>\n` +
        `      <div class="best-for"><strong>Best for:</strong> Data-heavy apps</div>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `</div>`, timestamp: '10:01 AM' },
      { sender: 'user', text: "I like the Bento Grid approach. Can you help me think through the grid structure for 1440px screens?", timestamp: '10:05 AM' },
      { sender: 'ai', text: `For a 1440px screen, a 12-column grid is standard. Here's a detailed Bento Grid specification:\n\n` +
        `<ul>\n` +
        `  <li><strong>Max Container Width:</strong> 1200px (leaving 120px margins on each side)</li>\n` +
        `  <li><strong>Columns:</strong> 12 columns, ~75px each</li>\n` +
        `  <li><strong>Gutter / Gap:</strong> 24px (standard 1.5rem)</li>\n` +
        `</ul>\n\n` +
        `<strong>Component Placement (Row by Row):</strong>\n` +
        `<ol>\n` +
        `  <li><strong>Top Row (Height 320px):</strong> Hero Metric takes 8 cols (left), Two small KPI tiles stack on the remaining 4 cols (right).</li>\n` +
        `  <li><strong>Middle Row (Height 400px):</strong> Main line chart spans 7 cols, Secondary pie chart spans 5 cols.</li>\n` +
        `  <li><strong>Bottom Row (Height 500px):</strong> Data table spans all 12 cols for maximum readability.</li>\n` +
        `</ol>\n\n` +
        `<strong>Responsive Breakpoints:</strong>\n` +
        `<ul>\n` +
        `  <li><strong>1024px:</strong> Reduce gaps to 16px. Hero metric spans 12 cols, KPIs move below.</li>\n` +
        `  <li><strong>768px:</strong> Switch to 8-column grid. Components stack vertically or in 2-col groups.</li>\n` +
        `</ul>`, timestamp: '10:06 AM' },
      { sender: 'user', text: "What about the mobile version? How should these cards stack?", timestamp: '10:08 AM' },
      { sender: 'ai', text: `For the mobile version (320px - 430px), here is the stacking strategy:\n\n` +
        `<strong>Priority-based Stacking Order:</strong>\n` +
        `<ol>\n` +
        `  <li><strong>Hero Metric:</strong> Place at the very top. This is the most critical piece of info.</li>\n` +
        `  <li><strong>Swipeable KPI Carousel:</strong> Instead of stacking 4 KPIs vertically (which pushes down charts), place them in a horizontal scrollable row with snap points.</li>\n` +
        `  <li><strong>Main Chart:</strong> Place below KPIs. Consider reducing data density or adding a "tap to expand" full-screen mode.</li>\n` +
        `  <li><strong>Secondary Charts:</strong> Place below main chart. If low priority, put them inside a collapsible accordion.</li>\n` +
        `  <li><strong>Data Table:</strong> Bottom. Since tables are awful on mobile, show a simplified list view instead, with a "View All Details" button.</li>\n` +
        `</ol>\n\n` +
        `<strong>Mobile specific tweaks:</strong> Increase font sizes for readability, ensure tap targets (buttons/links) are at least 44x44px.`, timestamp: '10:09 AM' }
    ]
  },
  'ui-copy': {
    id: 'ui-copy',
    title: 'UI Copy Generation',
    modeIcon: '✍️',
    color: '#1a9e5c', // careem teal
    preview: 'Onboarding flow microcopy',
    messages: [
      { sender: 'user', text: "We need compelling copy for our app's onboarding flow. It's a project management tool for creative teams. The tone should be friendly but professional.", timestamp: '11:00 AM' },
      { sender: 'ai', text: `Here is complete onboarding copy for 4 screens, tailored for creative teams with a friendly, professional tone.\n\n` +
        `<div class="copy-suggestions">\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">Welcome Screen</span>\n` +
        `    <div class="copy-content">\n` +
        `      <strong>Headline:</strong> Welcome to your creative command center.<br/>\n` +
        `      <em>Variant B:</em> Let's bring your best ideas to life.<br/><br/>\n` +
        `      <strong>Subtext:</strong> Organize projects, collaborate with your team, and deliver amazing work—all in one place.<br/><br/>\n` +
        `      <strong>CTA Button:</strong> Get Started\n` +
        `    </div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">Team Setup</span>\n` +
        `    <div class="copy-content">\n` +
        `      <strong>Headline:</strong> Who's on your creative squad?<br/>\n` +
        `      <strong>Description:</strong> Invite your team members so you can start collaborating right away.<br/><br/>\n` +
        `      <strong>Input Labels:</strong> Workspace Name, Teammate Emails<br/>\n` +
        `      <strong>Helper Text:</strong> Don't worry, you can always add more people later.\n` +
        `    </div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">First Project</span>\n` +
        `    <div class="copy-content">\n` +
        `      <strong>Headline:</strong> Let's kick off your first project.<br/>\n` +
        `      <strong>Description:</strong> Start from scratch or use one of our templates tailored for creative workflows.<br/><br/>\n` +
        `      <strong>Templates:</strong><br/>\n` +
        `      - Brand Identity: <em>Track assets, guidelines, and approvals.</em><br/>\n` +
        `      - Marketing Campaign: <em>Manage deliverables across channels.</em>\n` +
        `    </div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">All Set</span>\n` +
        `    <div class="copy-content">\n` +
        `      <strong>Headline:</strong> You're all set and ready to create!<br/>\n` +
        `      <strong>Body Text:</strong> Your workspace is configured. Dive in and start turning those concepts into reality.<br/><br/>\n` +
        `      <strong>Primary CTA:</strong> Go to My Dashboard<br/>\n` +
        `      <strong>Secondary CTA:</strong> Show me a quick tour\n` +
        `    </div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `</div>`, timestamp: '11:02 AM' },
      { sender: 'user', text: "Great! Now I need error messages and empty states for the projects page.", timestamp: '11:05 AM' },
      { sender: 'ai', text: `Here are error messages and empty states tailored for the projects page.\n\n` +
        `<strong>Error Messages</strong>\n` +
        `<div class="copy-suggestions">\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">Network Error</span>\n` +
        `    <div class="copy-content"><strong>Title:</strong> Connection lost<br/><strong>Description:</strong> We're having trouble connecting to the server. Please check your internet connection and try again.<br/><strong>Action:</strong> Try Again<br/><em style="color:#aaa;">Tone note: Direct and helpful, avoids blaming the user.</em></div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">Permission Denied</span>\n` +
        `    <div class="copy-content"><strong>Title:</strong> Access restricted<br/><strong>Description:</strong> It looks like you don't have permission to view this project. Reach out to the project owner for access.<br/><strong>Action:</strong> Request Access<br/><em style="color:#aaa;">Tone note: Polite, offers a clear next step.</em></div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">Not Found (404)</span>\n` +
        `    <div class="copy-content"><strong>Title:</strong> Project not found<br/><strong>Description:</strong> The project you're looking for might have been moved or deleted.<br/><strong>Action:</strong> Back to Dashboard<br/><em style="color:#aaa;">Tone note: Informative, guides user back to safety.</em></div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `</div>\n\n` +
        `<strong>Empty States</strong>\n` +
        `<div class="copy-suggestions">\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">First-Time User (No Projects)</span>\n` +
        `    <div class="copy-content"><strong>Title:</strong> Your creative canvas awaits<br/><strong>Description:</strong> You don't have any projects yet. Create your first one to start organizing your team's work.<br/><strong>Action:</strong> + New Project<br/><em style="color:#aaa;">Tone note: Inspiring and encouraging.</em></div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <span class="copy-label">No Results (Search/Filter)</span>\n` +
        `    <div class="copy-content"><strong>Title:</strong> No matches found<br/><strong>Description:</strong> We couldn't find any projects matching your search. Try adjusting your filters or search terms.<br/><strong>Action:</strong> Clear Filters<br/><em style="color:#aaa;">Tone note: Helpful and practical.</em></div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `</div>`, timestamp: '11:06 AM' },
      { sender: 'user', text: "Can you write tooltip copy for the main toolbar icons?", timestamp: '11:10 AM' },
      { sender: 'ai', text: `Here is the tooltip copy for 8 standard toolbar items, including short hover states and extended help mode descriptions.\n\n` +
        `<div class="copy-suggestions tooltip-grid">\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>➕ (New)</strong><br/><em>Short:</em> New Item<br/><em>Extended:</em> Create a new project, task, or document in the current workspace.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>🔍 (Search)</strong><br/><em>Short:</em> Search<br/><em>Extended:</em> Find projects, tasks, messages, and files across all your workspaces. (Cmd+K)</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>🔔 (Notifications)</strong><br/><em>Short:</em> Notifications<br/><em>Extended:</em> View recent activity, mentions, and updates from your team.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>⚙️ (Settings)</strong><br/><em>Short:</em> Settings<br/><em>Extended:</em> Manage your profile, workspace preferences, and billing details.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>👥 (Team)</strong><br/><em>Short:</em> Team Directory<br/><em>Extended:</em> View team members, manage roles, and invite new people.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>📊 (Reports)</strong><br/><em>Short:</em> Reports<br/><em>Extended:</em> Access analytics, project velocity, and time-tracking summaries.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>💬 (Messages)</strong><br/><em>Short:</em> Messages<br/><em>Extended:</em> Direct messages and project discussions with your team.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `  <div class="copy-card">\n` +
        `    <div class="copy-content"><strong>❓ (Help)</strong><br/><em>Short:</em> Help & Support<br/><em>Extended:</em> Access documentation, video tutorials, or contact our support team.</div>\n` +
        `    <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>\n` +
        `  </div>\n` +
        `</div>`, timestamp: '11:11 AM' }
    ]
  },
  'usability-feedback': {
    id: 'usability-feedback',
    title: 'Usability Feedback',
    modeIcon: '📊',
    color: '#0d8a3f', // careem dark green
    preview: 'Checkout flow redesign findings',
    messages: [
      { sender: 'user', text: "I just completed usability testing with 12 participants on our checkout flow redesign. Here's a summary of findings - can you help me organize and prioritize them? Issues found: confusing shipping options, unclear total price, too many form fields, missing progress indicator, small tap targets on mobile, unclear error messages, no guest checkout option, slow loading on payment step.", timestamp: '2:00 PM' },
      { sender: 'ai', text: `Here is a structured analysis of your usability testing findings, prioritized by severity.\n\n` +
        `<div class="feedback-container">\n` +
        `  <h4>Top 3 Priority Fixes</h4>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><span class="badge badge-critical">Critical</span> <strong>No guest checkout option</strong></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Rationale:</em> Forcing users to create an account is the #1 cause of cart abandonment.</p>\n` +
        `      <div class="metric-bar-container"><div class="metric-label">Task Drop-off</div><div class="metric-bar"><div class="metric-fill bg-red" style="width: 75%;">75%</div></div></div>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><span class="badge badge-critical">Critical</span> <strong>Unclear total price</strong></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Rationale:</em> Users need cost transparency (taxes, shipping) before the final step to trust the process.</p>\n` +
        `      <div class="metric-bar-container"><div class="metric-label">User Frustration</div><div class="metric-bar"><div class="metric-fill bg-red" style="width: 82%;">82%</div></div></div>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><span class="badge badge-high">High</span> <strong>Slow loading on payment step</strong></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Rationale:</em> Payment delays cause anxiety and duplicate submissions.</p>\n` +
        `      <div class="metric-bar-container"><div class="metric-label">Error Rate</div><div class="metric-bar"><div class="metric-fill bg-orange" style="width: 45%;">45%</div></div></div>\n` +
        `    </div>\n` +
        `  </div>\n\n` +
        `  <h4>Secondary Issues</h4>\n` +
        `  <ul class="feedback-list">\n` +
        `    <li><span class="badge badge-high">High</span> <strong>Confusing shipping options:</strong> Needs clearer descriptions and delivery dates.</li>\n` +
        `    <li><span class="badge badge-medium">Medium</span> <strong>Unclear error messages:</strong> Prevent users from recovering from mistakes easily.</li>\n` +
        `    <li><span class="badge badge-medium">Medium</span> <strong>Too many form fields:</strong> Causes fatigue. Consolidate or use auto-fill APIs.</li>\n` +
        `  </ul>\n\n` +
        `  <h4>Quick Wins (Low Effort, High Impact)</h4>\n` +
        `  <ul class="feedback-list">\n` +
        `    <li><span class="badge badge-low">Low</span> <strong>Small tap targets on mobile:</strong> Increase padding on buttons and links (CSS fix).</li>\n` +
        `    <li><span class="badge badge-low">Low</span> <strong>Missing progress indicator:</strong> Add a simple step wizard UI (e.g., Cart > Shipping > Payment).</li>\n` +
        `  </ul>\n` +
        `</div>`, timestamp: '2:02 PM' },
      { sender: 'user', text: "Can you create a summary I can present to stakeholders?", timestamp: '2:05 PM' },
      { sender: 'ai', text: `Here is an executive summary tailored for stakeholders.\n\n` +
        `<div class="executive-summary">\n` +
        `  <h2 style="color: #a8b2d1; margin-bottom: 0.5rem;">Checkout Redesign Usability Results</h2>\n` +
        `  <div class="stat-callout">\n` +
        `    <span class="big-stat">67%</span>\n` +
        `    <span class="stat-text">of users struggled to complete the checkout due to account barriers and price opacity.</span>\n` +
        `  </div>\n\n` +
        `  <h4>Key Takeaways</h4>\n` +
        `  <ul class="key-takeaways">\n` +
        `    <li><strong>Account Creation is a Blocker:</strong> Lack of guest checkout resulted in significant task abandonment.</li>\n` +
        `    <li><strong>Trust Requires Transparency:</strong> Users hesitated to proceed without seeing the final calculated cost early in the flow.</li>\n` +
        `    <li><strong>Friction Points Exist:</strong> Form fatigue and unclear error handling slowed down successful completions.</li>\n` +
        `  </ul>\n\n` +
        `  <h4>Recommended Action Items (Effort/Impact Matrix)</h4>\n` +
        `  <table class="styled-table">\n` +
        `    <thead><tr><th>Initiative</th><th>Impact</th><th>Effort</th></tr></thead>\n` +
        `    <tbody>\n` +
        `      <tr><td>Implement Guest Checkout</td><td><span style="color:#e74c3c;">High</span></td><td>Medium</td></tr>\n` +
        `      <tr><td>Persistent Order Summary (Total Price)</td><td><span style="color:#e74c3c;">High</span></td><td><span style="color:#2ecc71;">Low</span></td></tr>\n` +
        `      <tr><td>Increase mobile tap targets</td><td>Low</td><td><span style="color:#2ecc71;">Low</span></td></tr>\n` +
        `      <tr><td>Optimize payment gateway loading</td><td><span style="color:#e74c3c;">High</span></td><td>High</td></tr>\n` +
        `    </tbody>\n` +
        `  </table>\n\n` +
        `  <h4>Proposed Timeline</h4>\n` +
        `  <p>We recommend addressing the <strong>Low Effort/High Impact</strong> items (Order Summary, Tap Targets) in the next sprint, while dedicating design discovery for Guest Checkout implementation over the next 2 weeks.</p>\n` +
        `</div>`, timestamp: '2:06 PM' },
      { sender: 'user', text: "What usability heuristics were violated in our design?", timestamp: '2:10 PM' },
      { sender: 'ai', text: `Based on your findings, here is a mapping to <strong>Nielsen's 10 Usability Heuristics</strong>:\n\n` +
        `<div class="heuristic-analysis">\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><strong>1. Visibility of System Status</strong> <span class="badge badge-high">High</span></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Violations:</em> Missing progress indicator, slow loading on payment step without feedback.</p>\n` +
        `      <p><em>Recommendation:</em> Add a clear step wizard (1 of 3) and robust loading state animations (skeletons/spinners) during payment processing.</p>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><strong>3. User Control and Freedom</strong> <span class="badge badge-critical">Critical</span></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Violations:</em> No guest checkout option.</p>\n` +
        `      <p><em>Recommendation:</em> Allow users to complete the purchase without an account, offering account creation as an optional step post-purchase.</p>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><strong>9. Help Users Recognize, Diagnose, and Recover from Errors</strong> <span class="badge badge-medium">Medium</span></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Violations:</em> Unclear error messages.</p>\n` +
        `      <p><em>Recommendation:</em> Use plain language to describe what went wrong (e.g., "Card declined due to invalid CVV") and highlight the specific field needing correction.</p>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `  <div class="feedback-item">\n` +
        `    <div class="feedback-header"><strong>8. Aesthetic and Minimalist Design</strong> <span class="badge badge-medium">Medium</span></div>\n` +
        `    <div class="feedback-body">\n` +
        `      <p><em>Violations:</em> Too many form fields, confusing shipping options.</p>\n` +
        `      <p><em>Recommendation:</em> Remove optional fields, use address auto-complete, and simplify shipping choices into clear tiers (Standard, Express, Overnight).</p>\n` +
        `    </div>\n` +
        `  </div>\n` +
        `</div>`, timestamp: '2:11 PM' }
    ]
  }
};

// --- 2. App State Management ---
const state = {
  currentMode: 'layout-brainstorm', // 'layout-brainstorm' | 'ui-copy' | 'usability-feedback'
  currentConversation: 'layout-brainstorm',
  sidebarOpen: true, // false on mobile initially depending on screen size
  isTyping: false
};

// --- 3. Rendering Functions ---

function initApp() {
  injectCSS();
  setupDOM();
  
  // Set initial state based on window width
  state.sidebarOpen = window.innerWidth > 768;
  
  renderSidebar();
  renderApp();
  setupEventListeners();
}

function setupDOM() {
  // Clear body and set up main structure
  document.body.innerHTML = `
    <div id="app" class="app-container ${state.sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}">
      <aside id="sidebar" class="sidebar">
        <div class="sidebar-header">
          <h2><span class="logo-sparkle">✦</span> Design Companion</h2>
          <button id="close-sidebar-btn" class="mobile-only icon-btn">✕</button>
        </div>
        <div class="mode-selector" id="mode-selector"></div>
        <div class="conversation-list" id="conversation-list"></div>
        <div class="sidebar-footer" style="padding: 16px 20px; border-top: 1px solid var(--glass-border); margin-top: auto;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary); box-shadow: 0 0 8px rgba(40, 187, 78, 0.4);"></div>
            <span style="font-size: 0.8rem; color: var(--text-muted);">AI Prototype v1.0</span>
          </div>
        </div>
      </aside>
      <main id="main-content" class="main-content">
        <header class="main-header">
          <button id="open-sidebar-btn" class="icon-btn">☰</button>
          <div id="header-title" class="header-title"></div>
        </header>
        <div id="chat-container" class="chat-container">
          <div id="messages-container" class="messages-container"></div>
        </div>
        <div class="input-area">
          <div id="input-bar" class="input-bar"></div>
        </div>
      </main>
    </div>
  `;
}

function renderSidebar() {
  // Mode Selector
  const modeSelector = document.getElementById('mode-selector');
  modeSelector.innerHTML = `
    <div class="sidebar-section-title">Modes</div>
    ${Object.values(CONVERSATIONS).map(conv => `
      <button class="mode-btn ${state.currentMode === conv.id ? 'active' : ''}" 
              data-mode="${conv.id}" 
              onclick="switchMode('${conv.id}')">
        <span class="mode-dot" style="background-color: ${conv.color}"></span>
        <span class="mode-icon">${conv.modeIcon}</span>
        <span class="mode-name">${conv.title}</span>
      </button>
    `).join('')}
  `;

  // Conversation List
  const convList = document.getElementById('conversation-list');
  convList.innerHTML = `
    <div class="sidebar-section-title">Recent Conversations</div>
    ${Object.values(CONVERSATIONS).map(conv => `
      <div class="conversation-item ${state.currentConversation === conv.id ? 'active' : ''}" 
           onclick="switchMode('${conv.id}')">
        <div class="conv-icon">${conv.modeIcon}</div>
        <div class="conv-details">
          <div class="conv-title">${conv.title}</div>
          <div class="conv-preview">${conv.preview}</div>
        </div>
      </div>
    `).join('')}
  `;
}

function renderApp() {
  const currentConv = CONVERSATIONS[state.currentConversation];
  
  // Header title
  document.getElementById('header-title').innerHTML = `
    <span class="header-mode-icon">${currentConv.modeIcon}</span>
    ${currentConv.title}
    <span class="header-badge" style="
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: ${currentConv.color}20;
      color: ${currentConv.color};
      border: 1px solid ${currentConv.color}40;
      margin-left: 8px;
    ">Active</span>
    <span style="margin-left: auto; font-size: 0.8rem; color: var(--accent-primary); font-weight: 600; background: var(--accent-primary-light); padding: 4px 10px; border-radius: 12px; border: 1px solid rgba(40, 187, 78, 0.3);">Live AI Mode</span>
  `;

  // Render Messages
  renderMessages(state.currentConversation);
  
  // Render Input Bar
  renderInputBar();
}

function renderMessages(conversationId) {
  const container = document.getElementById('messages-container');
  const messages = CONVERSATIONS[conversationId].messages;
  
  container.innerHTML = messages.map((msg, index) => {
    const isUser = msg.sender === 'user';
    return `
      <div class="message-wrapper ${isUser ? 'user-wrapper' : 'ai-wrapper'}" style="animation-delay: ${index * 0.15}s">
        ${!isUser ? `<div class="avatar ai-avatar">✦</div>` : ''}
        <div class="message ${isUser ? 'user-message' : 'ai-message'} mode-${state.currentMode}">
          <div class="message-content">${msg.text}</div>
          <div class="message-timestamp">${msg.timestamp}</div>
        </div>
        ${isUser ? `<div class="avatar user-avatar">U</div>` : ''}
      </div>
    `;
  }).join('');
  
  if (state.isTyping) {
    container.innerHTML += `
      <div class="message-wrapper ai-wrapper typing-indicator-wrapper">
        <div class="avatar ai-avatar">✦</div>
        <div class="message ai-message typing-message">
          <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
      </div>
    `;
  }
  
  scrollToBottom();
}

function renderInputBar() {
  const inputBar = document.getElementById('input-bar');
  const currentConv = CONVERSATIONS[state.currentConversation];
  
  let placeholder = "Type a message...";
  if (state.currentMode === 'layout-brainstorm') placeholder = "Ask about layout grids, responsiveness, etc...";
  if (state.currentMode === 'ui-copy') placeholder = "Ask for button copy, error states, tooltips...";
  if (state.currentMode === 'usability-feedback') placeholder = "Paste testing notes to summarize...";

  inputBar.innerHTML = `
    <div class="input-actions">
      <div class="input-chip" style="color: ${currentConv.color}; border-color: ${currentConv.color}40; background: ${currentConv.color}10;">
        ${currentConv.modeIcon} ${currentConv.title} Mode
      </div>
      <div class="prototype-note">Powered by OpenRouter</div>
    </div>
    <div style="display: flex; gap: 12px; align-items: flex-end;">
      <textarea 
        id="chat-input" 
        placeholder="${placeholder}" 
        rows="1"
        oninput="autoResize(this)"
      ></textarea>
      <button class="send-btn" onclick="handleSend()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
  `;
  
  // Enter key support
  document.getElementById('chat-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });
}

// --- 4. Event Handlers & Interactions ---

function setupEventListeners() {
  document.getElementById('open-sidebar-btn').addEventListener('click', toggleSidebar);
  document.getElementById('close-sidebar-btn').addEventListener('click', toggleSidebar);
  
  window.addEventListener('resize', () => {
    if (window.innerWidth > 768 && !state.sidebarOpen) {
      toggleSidebar(true);
    } else if (window.innerWidth <= 768 && state.sidebarOpen) {
      toggleSidebar(false);
    }
  });
}

window.switchMode = function(modeId) {
  if (state.currentMode === modeId) return;
  
  state.currentMode = modeId;
  state.currentConversation = modeId;
  
  // Re-render UI
  renderSidebar();
  
  const container = document.getElementById('messages-container');
  container.style.opacity = 0;
  
  setTimeout(() => {
    renderApp();
    container.style.opacity = 1;
    if (window.innerWidth <= 768) {
      toggleSidebar(false);
    }
  }, 200);
};

window.toggleSidebar = function(forceState) {
  state.sidebarOpen = forceState !== undefined ? forceState : !state.sidebarOpen;
  const app = document.getElementById('app');
  
  if (state.sidebarOpen) {
    app.classList.remove('sidebar-closed');
    app.classList.add('sidebar-open');
  } else {
    app.classList.remove('sidebar-open');
    app.classList.add('sidebar-closed');
  }
};

window.handleSend = async function() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  
  if (!text || state.isTyping) return;
  
  // Add user message
  const currentConv = CONVERSATIONS[state.currentConversation];
  currentConv.messages.push({
    sender: 'user',
    text: escapeHTML(text),
    timestamp: formatTimestamp(new Date())
  });
  
  input.value = '';
  input.style.height = 'auto';
  
  // Show typing indicator
  state.isTyping = true;
  renderMessages(state.currentConversation);
  
  // Call real AI API
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: currentConv.messages,
        mode: state.currentMode
      })
    });
    
    const data = await response.json();
    
    state.isTyping = false;
    
    if (response.ok) {
      currentConv.messages.push({
        sender: 'ai',
        text: data.text,
        timestamp: formatTimestamp(new Date())
      });
    } else {
      currentConv.messages.push({
        sender: 'ai',
        text: `<div class="static-notice" style="border-color: red; color: red;"><strong>Error:</strong> ${data.error || 'Failed to connect to AI.'}</div>`,
        timestamp: formatTimestamp(new Date())
      });
    }
  } catch (error) {
    state.isTyping = false;
    currentConv.messages.push({
      sender: 'ai',
      text: `<div class="static-notice" style="border-color: red; color: red;"><strong>Network Error:</strong> ${error.message} - Make sure the Vercel deployment completed successfully.</div>`,
      timestamp: formatTimestamp(new Date())
    });
  }
  
  renderMessages(state.currentConversation);
};

window.copyToClipboard = function(buttonElem) {
  const card = buttonElem.closest('.copy-card');
  const content = card.querySelector('.copy-content').innerText;
  
  navigator.clipboard.writeText(content).then(() => {
    const originalText = buttonElem.innerText;
    buttonElem.innerText = 'Copied! ✓';
    buttonElem.classList.add('success');
    
    setTimeout(() => {
      buttonElem.innerText = originalText;
      buttonElem.classList.remove('success');
    }, 2000);
  });
};

window.autoResize = function(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = textarea.scrollHeight + 'px';
  if (textarea.scrollHeight > 150) {
    textarea.style.overflowY = 'auto';
  } else {
    textarea.style.overflowY = 'hidden';
  }
};

// --- 5. Utility Functions ---

function scrollToBottom() {
  const container = document.getElementById('chat-container');
  requestAnimationFrame(() => {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth'
    });
  });
}

function formatTimestamp(date) {
  let hours = date.getHours();
  let minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? hours : 12;
  minutes = minutes < 10 ? '0' + minutes : minutes;
  return hours + ':' + minutes + ' ' + ampm;
}

function escapeHTML(str) {
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag])
  );
}

// --- 6. Styles Injection (Light Theme, Careem Green) ---

function injectCSS() {
  const style = document.createElement('style');
  style.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
      --bg-color: #ffffff;
      --sidebar-bg: #fdfdfd;
      --card-bg: #ffffff;
      --glass-border: #f0f0f0;
      --text-main: #111827;
      --text-muted: #6b7280;
      
      --accent-primary: #28BB4E;
      --accent-primary-light: #e8f8ed;
      --accent-primary-dark: #1a9e3e;
      --accent-purple: #28BB4E;
      --accent-blue: #1a9e5c;
      --accent-green: #0d8a3f;
      
      --user-msg-bg: #28BB4E;
      --ai-msg-bg: #ffffff;
      
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 16px;
      
      --shadow-sm: none;
      --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.04);
      --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.06);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-color);
      color: var(--text-main);
      overflow: hidden;
      height: 100vh;
      display: flex;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    ::selection {
      background-color: rgba(40, 187, 78, 0.2);
      color: #1a2e22;
    }

    ::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    ::-webkit-scrollbar-track {
      background: transparent;
    }
    ::-webkit-scrollbar-thumb {
      background: rgba(0, 0, 0, 0.12);
      border-radius: 9999px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: rgba(0, 0, 0, 0.2);
    }

    .app-container {
      display: flex;
      width: 100%;
      height: 100%;
      transition: all 0.3s ease;
    }

    /* Sidebar */
    .sidebar {
      width: 280px;
      background-color: var(--sidebar-bg);
      border-right: 1px solid var(--glass-border);
      display: flex;
      flex-direction: column;
      transition: transform 0.3s ease, width 0.3s ease;
      z-index: 100;
      box-shadow: 1px 0 0 var(--glass-border);
    }
    
    .sidebar-closed .sidebar {
      transform: translateX(-100%);
      width: 0;
      border: none;
    }

    .sidebar-header {
      padding: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--glass-border);
    }

    .sidebar-header h2 {
      font-size: 1.1rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .logo-sparkle {
      color: var(--accent-primary);
      font-size: 1.3rem;
    }

    .sidebar-section-title {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      padding: 20px 20px 10px 20px;
      font-weight: 600;
    }

    .mode-selector, .conversation-list {
      display: flex;
      flex-direction: column;
      padding: 0 10px;
    }

    .mode-btn, .conversation-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      background: transparent;
      border: none;
      border-radius: var(--radius-md);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s ease;
      text-align: left;
      margin-bottom: 4px;
    }

    .mode-btn:hover, .conversation-item:hover {
      background-color: var(--accent-primary-light);
      color: var(--text-main);
    }

    .mode-btn.active, .conversation-item.active {
      background-color: var(--accent-primary-light);
      color: var(--accent-primary-dark);
      box-shadow: inset 3px 0 0 var(--accent-primary);
      font-weight: 600;
    }

    .mode-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }

    .conv-icon {
      font-size: 1.2rem;
    }
    .conv-details {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .conv-title {
      font-size: 0.9rem;
      font-weight: 500;
      white-space: nowrap;
      text-overflow: ellipsis;
      overflow: hidden;
    }
    .conv-preview {
      font-size: 0.8rem;
      color: var(--text-muted);
      white-space: nowrap;
      text-overflow: ellipsis;
      overflow: hidden;
    }

    /* Main Content */
    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100vh;
      position: relative;
    }

    .main-header {
      height: 64px;
      padding: 0 24px;
      display: flex;
      align-items: center;
      gap: 16px;
      border-bottom: 1px solid var(--glass-border);
      background: var(--bg-color);
      position: sticky;
      top: 0;
      z-index: 10;
    }

    .header-title {
      font-weight: 600;
      font-size: 1.1rem;
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
    }

    .icon-btn {
      background: transparent;
      border: none;
      color: var(--text-main);
      font-size: 1.2rem;
      cursor: pointer;
      padding: 8px;
      border-radius: var(--radius-sm);
      transition: background 0.2s;
    }
    .icon-btn:hover { background: var(--accent-primary-light); }

    /* Chat Area */
    .chat-container {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      scroll-behavior: smooth;
      background: var(--bg-color);
    }

    .messages-container {
      max-width: 800px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 24px;
      padding-bottom: 40px;
      transition: opacity 0.2s ease;
    }

    .message-wrapper {
      display: flex;
      gap: 16px;
      align-items: flex-end;
      opacity: 0;
      transform: translateY(20px);
      animation: fadeInUp 0.5s ease forwards;
    }
    
    @keyframes fadeInUp {
      to { opacity: 1; transform: translateY(0); }
    }

    .user-wrapper {
      justify-content: flex-end;
    }

    .avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      flex-shrink: 0;
    }

    .ai-avatar {
      background: var(--bg-color);
      color: var(--accent-primary);
      border: 1px solid var(--glass-border);
    }

    .user-avatar {
      background: var(--text-main);
      color: #fff;
    }

    .message {
      max-width: 85%;
      padding: 14px 18px;
      border-radius: var(--radius-lg);
      font-size: 0.95rem;
      line-height: 1.6;
    }

    .user-message {
      background: var(--user-msg-bg);
      border-bottom-right-radius: 4px;
      color: #fff;
    }

    .ai-message {
      background: transparent;
      padding-left: 0;
    }

    .ai-message.mode-layout-brainstorm,
    .ai-message.mode-ui-copy,
    .ai-message.mode-usability-feedback {
      border-left: none;
    }

    .message-timestamp {
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-top: 8px;
      text-align: right;
    }
    .user-message .message-timestamp {
      color: rgba(255, 255, 255, 0.8);
    }

    /* Input Area */
    .input-area {
      padding: 24px;
      background: var(--bg-color);
      border-top: 1px solid var(--glass-border);
    }

    .input-bar {
      max-width: 800px;
      margin: 0 auto;
      background: var(--bg-color);
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-md);
      padding: 12px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      box-shadow: var(--shadow-md);
      transition: border-color 0.3s ease, box-shadow 0.3s ease;
    }
    .input-bar:focus-within {
      border-color: #d1d5db;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    }

    .input-chip {
      align-self: flex-start;
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 12px;
      border: 1px solid;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    #chat-input {
      width: 100%;
      background: transparent;
      border: none;
      color: var(--text-main);
      font-family: inherit;
      font-size: 1rem;
      resize: none;
      outline: none;
      max-height: 150px;
    }
    
    #chat-input::placeholder { color: var(--text-muted); }

    .input-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .prototype-note {
      font-size: 0.75rem;
      color: var(--text-muted);
      font-style: italic;
    }

    .send-btn {
      background: var(--user-msg-bg);
      border: none;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      cursor: pointer;
      transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .send-btn:hover {
      transform: scale(1.05);
      box-shadow: 0 4px 16px rgba(40, 187, 78, 0.35);
    }
    .send-btn:active { transform: scale(0.95); }

    /* Typing Indicator */
    .typing-dots span {
      display: inline-block;
      width: 6px;
      height: 6px;
      background-color: var(--text-muted);
      border-radius: 50%;
      margin: 0 2px;
      animation: bounce 1.4s infinite ease-in-out both;
    }
    .typing-dots span:nth-child(1) { animation-delay: -0.32s; }
    .typing-dots span:nth-child(2) { animation-delay: -0.16s; }
    
    @keyframes bounce {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }
    
    .static-notice {
      padding: 12px 14px;
      background: var(--accent-primary-light);
      border-left: 3px solid var(--accent-primary);
      border-radius: 6px;
      color: var(--accent-primary-dark);
      font-size: 0.9rem;
    }

    /* --- Rich UI Components within AI Messages --- */
    
    /* Layout Cards */
    .layout-cards { display: flex; flex-direction: column; gap: 20px; margin-top: 15px; }
    .layout-card {
      background: var(--card-bg);
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-md);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .layout-card:hover {
      transform: translateY(-3px);
      box-shadow: var(--shadow-lg), 0 0 0 1px rgba(40, 187, 78, 0.15);
    }
    
    .layout-viz {
      height: 160px;
      background: #f9fafb;
      padding: 15px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow: hidden;
      position: relative;
    }
    .layout-viz * { min-height: 0; }
    .layout-viz .box { background: #f3f4f6; border-radius: 6px; border: 1px solid #e5e7eb; width: 100%; height: 100%; min-height: 20px; }
    
    .z-pattern .kpi-row { display: flex; gap: 8px; height: 30%; width: 100%; }
    .z-pattern .kpi-row .box { flex: 1; }
    .z-pattern .chart-row { display: flex; gap: 8px; height: 45%; width: 100%; }
    .z-pattern .main-chart { flex: 2; }
    .z-pattern .side-chart { flex: 1; }
    .z-pattern .table-row { height: 25%; width: 100%; }
    .z-pattern .full-table { height: 100%; width: 100%; }
    
    .bento-grid { display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 8px; height: 100%; }
    .bento-grid .hero { grid-row: span 2; }
    
    .command-center { display: flex; flex-direction: column; gap: 8px; height: 100%; }
    .command-center .top-nav { height: 20%; width: 100%; }
    .command-center .split-view { display: flex; gap: 8px; height: 80%; width: 100%; }
    .command-center .sidebar { flex: 1; }
    .command-center .main-content { flex: 3; }

    .layout-details { padding: 16px; }
    .layout-details h3 { margin-bottom: 8px; color: var(--accent-primary-dark); font-size: 1.1rem; }
    .layout-details p { font-size: 0.9rem; color: var(--text-muted); margin-bottom: 12px; }
    .pros-cons { display: flex; gap: 16px; font-size: 0.85rem; margin-bottom: 12px; }
    .pro-icon { color: var(--accent-primary); }
    .con-icon { color: #e74c3c; }
    .best-for { font-size: 0.85rem; padding: 8px 12px; background: var(--accent-primary-light); border-radius: 6px; color: var(--accent-primary-dark); }

    /* Copy Suggestions */
    .copy-suggestions { display: flex; flex-direction: column; gap: 16px; margin: 15px 0; }
    .tooltip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .copy-card {
      background: #f8faf9;
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-sm);
      padding: 16px;
      position: relative;
    }
    .copy-label {
      position: absolute;
      top: -10px;
      left: 16px;
      background: var(--accent-primary);
      color: white;
      font-size: 0.7rem;
      padding: 2px 10px;
      border-radius: 10px;
      font-weight: 600;
    }
    .copy-content { font-size: 0.9rem; margin-bottom: 16px; margin-top: 8px; color: var(--text-main); }
    .btn-copy {
      background: #f3f4f6;
      border: 1px solid #e5e7eb;
      color: #374151;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-copy:hover { background: #e5e7eb; color: #111827; }
    .btn-copy.success { background: #111827; color: white; border-color: #111827; }

    /* Feedback Analytics */
    .feedback-container { margin-top: 15px; }
    .feedback-container h4 { margin: 20px 0 10px 0; color: var(--text-main); border-bottom: 1px solid var(--glass-border); padding-bottom: 8px; font-size: 0.95rem; }
    .feedback-item { background: #f8faf9; border-radius: var(--radius-sm); padding: 14px; margin-bottom: 12px; border: 1px solid var(--glass-border); }
    .feedback-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
    .badge { padding: 3px 10px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
    .badge-critical { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
    .badge-high { background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa; }
    .badge-medium { background: #fefce8; color: #ca8a04; border: 1px solid #fef08a; }
    .badge-low { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; }
    
    .metric-bar-container { margin-top: 10px; }
    .metric-label { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; display: flex; justify-content: space-between; }
    .metric-bar { height: 16px; background: #f0f4f1; border-radius: 8px; overflow: hidden; }
    .metric-fill { height: 100%; display: flex; align-items: center; padding-right: 8px; justify-content: flex-end; font-size: 0.65rem; font-weight: bold; color: white; border-radius: 8px; }
    .bg-red { background: linear-gradient(90deg, #dc2626, #ef4444); }
    .bg-orange { background: linear-gradient(90deg, #ea580c, #f97316); }
    
    .feedback-list { padding-left: 20px; font-size: 0.9rem; color: var(--text-muted); }
    .feedback-list li { margin-bottom: 8px; }
    
    .stat-callout { background: #f9fafb; border-left: 4px solid #111827; padding: 16px; display: flex; align-items: center; gap: 15px; margin: 15px 0; border-radius: 0 8px 8px 0; }
    .big-stat { font-size: 2.5rem; font-weight: 700; color: #111827; line-height: 1; }
    
    .styled-table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 0.85rem; }
    .styled-table th, .styled-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--glass-border); }
    .styled-table th { color: var(--text-muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.3px; }
    
    /* Lists */
    .ai-message ul, .ai-message ol { padding-left: 20px; margin: 10px 0; }
    .ai-message li { margin-bottom: 5px; }

    /* Media Queries */
    @media (min-width: 769px) {
      .mobile-only { display: none !important; }
    }
    
    @media (max-width: 768px) {
      .sidebar {
        position: absolute;
        height: 100%;
        box-shadow: 5px 0 25px rgba(0,0,0,0.1);
      }
      .tooltip-grid { grid-template-columns: 1fr; }
      .message { max-width: 95%; }
    }
  `;
  document.head.appendChild(style);
}

// Start app on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
