---
name: Legal Desk project status
description: Current status of the Legal Desk Webflow build including modal, nav, footer, localization, and article template as of 2026-03-22
type: project
---

## Architecture Decisions
- Modal lives INSIDE the Navigation component (not standalone) — available on all pages automatically
- modal-overlay has display:none set in Webflow style (not just CSS injection) so designer doesn't block
- 3 page types planned: Article/Product (shared CMS template with CTA toggle), Landing pages (custom static pages with premade components)
- URL structure: flat CMS slugs (e.g., /artikler/slug) with breadcrumbs showing hierarchy. Locales use subdirectories (/se/, /no/)
- Localization via Webflow built-in: text overrides on components via Data API, locale visibility for logos/payment icons

## Completed
- Modal: All 4 steps, right column with swirl, proper Webflow elements + assets, responsive
- Navigation: Component with hamburger menu (v3.1.0), two-level accordion, sticky, localized SE/NO, modal inside it
- Footer: Component with correct text, logos, social icons, localized SE/NO. Backup component exists.
- Localization: Text overrides for SE (sv-SE) and NO (no-NO) on both nav + footer components via Data API
- Hamburger menu reads all content dynamically from DOM — works across locales, splits categories by index (0-7 Privat, 8-14 Erhverv)
- Nav-main-bar breakpoint styles set directly in Webflow (mobile 16px, tablet 24px, desktop 80px)
- Trustpilot Carousel component created (template-id: 54ad5defc6454f065c28af8b, 240px height, 4-5 stars, da-DK)
- Article template started: breadcrumb, 3-column layout (TOC sidebar, content, right sidebar), placeholder content
- Article styles extracted from source CSS (sector_content.css, rte-styles.css, main_general.css): H1 Inter 700 36px, H2 Inter 900 26px, H3 Inter 600 18px, body Barlow 16px black, TOC orange #F65734
- Page background: #f8f8f8 gray (via CSS injection on article page)
- Scripts: 8 on Home page, 9 on Article page (+article_page_styles)

## In Progress — Article/Product Template
- Basic structure built: breadcrumb, 3-column layout, TOC sidebar, content area with H2 sections, right sidebar placeholder
- Styles match source page CSS (extracted from legaldesk.dk)
- Needs: CMS collection setup, CTA toggle field, rich text styling, right sidebar product card, responsive breakpoints, more content sections

## Remaining — General
- Footer/Nav logo: swap to Jurio for SE and NO (locale visibility conditions in designer)
- Footer payment icons: need SE and NO SVGs, then locale visibility
- Floating label inputs (skipped — using placeholder)
- Phase 3: Selective Umbraco→Webflow CMS migration (separate project at ~/projects/umbraco-to-webflow-migration/) — not a wholesale migration, only importing and restructuring what's needed
- CVR lookup, password reset link, social login OAuth (blocked on backend)
- Password eye toggle JS (icons placed, toggle behavior removed during cleanup)
- "Navbar old" component cleanup (legacy instances to delete)
- Empty Kontakt item in footer (delete in designer)
- Component library for landing pages (hero, USP grid, social proof, CTA section, pricing)

## Key Source CSS Files (extracted from legaldesk.dk)
- /css/custom/sector_content.css — article layout, sidebar, breadcrumbs, headings
- /css/rte-styles.css — rich text editor overrides for article H2/H3
- /css/custom/main_general.css — global body, h1-h6, paragraph styles (body bg #f8f8f8, p font Barlow)
- /css/custom/side-nav.css — side navigation styles
- /css/custom/main.css — main hero and search styles

**Why:** Tracks progress across sessions for this multi-day Webflow build project.
**How to apply:** Reference when resuming work on Legal Desk or preparing backend handoff.
