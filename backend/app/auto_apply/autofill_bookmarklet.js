/**
 * AI Job Finder — 1-Click Universal Auto-Fill Script
 * =================================================
 * Compatible with:
 *  - Greenhouse (boards.greenhouse.io)
 *  - Lever (jobs.lever.co)
 *  - Ashby (jobs.ashbyhq.com)
 *  - Workday (myworkdayjobs.com)
 *  - LinkedIn Easy Apply & Generic Career Portals
 * 
 * Instructions:
 * 1. Bookmarklet: Save as a browser bookmark with URL: javascript:(function(){...code...})();
 * 2. Or paste directly into browser DevTools Console (F12) on any application page.
 */

(function () {
  const PROFILE = {
    firstName: "Akash",
    lastName: "Jadhav",
    fullName: "Akash R Jadhav",
    email: "akashrj090@gmail.com",
    phone: "+91 7676265783",
    rawPhone: "7676265783",
    location: "Bengaluru, Karnataka, India",
    city: "Bengaluru",
    country: "India",
    linkedin: "https://www.linkedin.com/in/akashrjadhav/",
    github: "https://github.com/akashrdj/portfolio",
    portfolio: "https://github.com/akashrdj/portfolio",
    university: "PES University",
    degree: "B.Tech in Computer Science and Engineering",
    graduationYear: "2026",
    noticePeriod: "Immediate (0 days)",
    workAuth: "Yes",
    needSponsorship: "No",
    yearsOfExp: "0",
  };

  let filledCount = 0;

  function triggerEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function setInputValue(el, value) {
    if (!el || !value) return false;
    el.focus();
    el.value = value;
    triggerEvents(el);
    filledCount++;
    return true;
  }

  function selectOption(selectEl, matchText) {
    if (!selectEl) return false;
    const lower = matchText.toLowerCase();
    for (let opt of selectEl.options) {
      if (opt.text.toLowerCase().includes(lower) || opt.value.toLowerCase().includes(lower)) {
        selectEl.value = opt.value;
        triggerEvents(selectEl);
        filledCount++;
        return true;
      }
    }
    return false;
  }

  console.log("%c[AI Job Finder] Auto-filling candidate fields...", "color: #3b82f6; font-weight: bold; font-size: 14px;");

  // 1. First Name & Last Name & Full Name
  const firstSelectors = [
    'input[name*="first_name" i]', 'input[id*="first_name" i]',
    'input[name*="firstname" i]', 'input[id*="firstname" i]',
    'input[autocomplete="given-name"]', 'input[placeholder*="first name" i]'
  ];
  const lastSelectors = [
    'input[name*="last_name" i]', 'input[id*="last_name" i]',
    'input[name*="lastname" i]', 'input[id*="lastname" i]',
    'input[autocomplete="family-name"]', 'input[placeholder*="last name" i]'
  ];
  const fullSelectors = [
    'input[name="name"]', 'input[name*="full_name" i]', 'input[id*="full_name" i]',
    'input[name="_systemfield_name"]', 'input[placeholder*="full name" i]',
    'input[autocomplete="name"]'
  ];

  let firstNameSet = false;
  for (let s of firstSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { firstNameSet = setInputValue(el, PROFILE.firstName); break; }
  }
  for (let s of lastSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.lastName); break; }
  }
  if (!firstNameSet) {
    for (let s of fullSelectors) {
      const el = document.querySelector(s);
      if (el && !el.value) { setInputValue(el, PROFILE.fullName); break; }
    }
  }

  // 2. Email Address
  const emailSelectors = [
    'input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]',
    'input[name="_systemfield_email"]', 'input[autocomplete="email"]'
  ];
  for (let s of emailSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.email); break; }
  }

  // 3. Phone Number
  const phoneSelectors = [
    'input[type="tel"]', 'input[name*="phone" i]', 'input[id*="phone" i]',
    'input[name="_systemfield_phoneNumber"]', 'input[autocomplete="tel"]'
  ];
  for (let s of phoneSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.phone); break; }
  }

  // 4. Location / City / Address
  const locSelectors = [
    'input[name*="location" i]', 'input[id*="location" i]',
    'input[name*="city" i]', 'input[id*="city" i]',
    'input[name*="candidate_location" i]'
  ];
  for (let s of locSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.location); break; }
  }

  // 5. LinkedIn Profile URL
  const linkedinSelectors = [
    'input[name*="linkedin" i]', 'input[id*="linkedin" i]',
    'input[name="urls[LinkedIn]"]', 'input[placeholder*="linkedin" i]'
  ];
  for (let s of linkedinSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.linkedin); break; }
  }

  // 6. GitHub Profile URL
  const githubSelectors = [
    'input[name*="github" i]', 'input[id*="github" i]',
    'input[name="urls[GitHub]"]', 'input[placeholder*="github" i]'
  ];
  for (let s of githubSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.github); break; }
  }

  // 7. Portfolio / Website URL
  const portfolioSelectors = [
    'input[name*="portfolio" i]', 'input[id*="portfolio" i]',
    'input[name*="website" i]', 'input[id*="website" i]',
    'input[name="urls[Portfolio]"]'
  ];
  for (let s of portfolioSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.portfolio); break; }
  }

  // 8. University / College / Organization
  const schoolSelectors = [
    'input[name*="school" i]', 'input[id*="school" i]',
    'input[name*="university" i]', 'input[id*="university" i]',
    'input[name="org"]'
  ];
  for (let s of schoolSelectors) {
    const el = document.querySelector(s);
    if (el && !el.value) { setInputValue(el, PROFILE.university); break; }
  }

  // 9. Standard Screening Dropdowns (Work Auth & Notice Period)
  const allSelects = document.querySelectorAll('select');
  allSelects.forEach((sel) => {
    const labelText = (sel.labels && sel.labels[0] ? sel.labels[0].innerText : "") + " " + (sel.name || "") + " " + (sel.id || "");
    const l = labelText.toLowerCase();

    if (l.includes("authorized") || l.includes("sponsorship") || l.includes("visa")) {
      if (l.includes("require") || l.includes("need") || l.includes("sponsorship")) {
        selectOption(sel, "no");
      } else {
        selectOption(sel, "yes");
      }
    } else if (l.includes("notice") || l.includes("join") || l.includes("availability")) {
      selectOption(sel, "immediate") || selectOption(sel, "0") || selectOption(sel, "15");
    } else if (l.includes("experience") || l.includes("yoe")) {
      selectOption(sel, "0") || selectOption(sel, "fresher");
    }
  });

  // Visual Banner Notification
  const banner = document.createElement("div");
  banner.style.cssText = `
    position: fixed; top: 16px; right: 16px; z-index: 999999;
    background: #0f172a; color: #f8fafc; border: 2px solid #3b82f6;
    border-radius: 8px; padding: 12px 18px; font-family: sans-serif;
    font-size: 13px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    display: flex; align-items: center; gap: 10px;
  `;
  banner.innerHTML = `
    <span style="font-size: 18px;">🚀</span>
    <div>
      <div style="font-weight: bold; color: #60a5fa;">AI Job Finder Autofill</div>
      <div style="color: #94a3b8;">Populated <b>${filledCount}</b> fields for Akash R Jadhav</div>
    </div>
  `;
  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 4000);

  return `[AI Job Finder] Filled ${filledCount} fields successfully!`;
})();
