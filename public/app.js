// When Flask serves this client, requests stay on the same deployed origin.
// The override remains useful when developing the frontend against another API.
const API_BASE = (window.CAMPUSCONNECT_API_URL || localStorage.getItem('campusconnect_api_url') || window.location.origin).replace(/\/$/, '');
const STORAGE_KEY = 'campusconnect_user_id';
const DEMO_ROLE_KEY = 'campusconnect_demo_role';
const DEMO_EVENTS_KEY = 'campusconnect_demo_events';
const DEMO_REGISTRATIONS_KEY = 'campusconnect_demo_registrations';
let state = { page: 'home', events: [], registrations: [], query: '', loading: true, authEnabled: false, organizerAuthenticated: false, organizerUsername: '' };
const demoEvents = [
  { id: 'demo-ai-workshop', title: 'AI & Machine Learning Workshop', event_date: demoDate(3), location: 'Innovation Lab', category: 'Workshop', capacity: 60, description: 'Build your first machine-learning model with guidance from campus mentors.', is_demo: true },
  { id: 'demo-hackathon', title: 'Campus Buildathon 2026', event_date: demoDate(7), location: 'Engineering Block', category: 'Hackathon', capacity: 120, description: 'Team up, prototype an idea, and present it to the campus community.', is_demo: true },
  { id: 'demo-cultural-night', title: 'Rhythm & Roots Cultural Night', event_date: demoDate(12), location: 'Open Air Theatre', category: 'Culture', capacity: 300, description: 'An evening of student performances, music, and cultural showcases.', is_demo: true },
  { id: 'demo-career-talk', title: 'Careers in Cloud & Cybersecurity', event_date: demoDate(18), location: 'Seminar Hall 2', category: 'Career Talk', capacity: 90, description: 'Hear industry stories and ask questions during an interactive alumni panel.', is_demo: true },
];

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const isDemoOrganizer = () => localStorage.getItem(DEMO_ROLE_KEY) !== 'student';
function demoDate(daysFromNow) { const date = new Date(); date.setHours(12,0,0,0); date.setDate(date.getDate() + daysFromNow); return date.toISOString(); }
const eventDate = (event) => new Date(event.event_date || event.date || event.starts_at || event.created_at);
const prettyDate = (event) => { const date = eventDate(event); return Number.isNaN(date.getTime()) ? 'Date TBA' : new Intl.DateTimeFormat('en-IN',{day:'2-digit',month:'short',year:'numeric'}).format(date); };
const day = (event) => { const date = eventDate(event); return Number.isNaN(date.getTime()) ? '—' : String(date.getDate()).padStart(2,'0'); };
const month = (event) => { const date = eventDate(event); return Number.isNaN(date.getTime()) ? 'TBA' : new Intl.DateTimeFormat('en-IN',{month:'short'}).format(date); };
const userId = () => localStorage.getItem(STORAGE_KEY) || '';
const isUuid = (value) => /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);

function api(path, options = {}) { return fetch(`${API_BASE}${path}`, { credentials:'include', ...options, headers: { 'Content-Type':'application/json', ...(userId() ? {'X-User-Id':userId()} : {}), ...(options.headers || {}) } }).then(async response => { const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || 'Something went wrong.'); return data; }); }
function icon(value) { return `<span class="icon">${value}</span>`; }
function layout(content) { const name = localStorage.getItem('campusconnect_name') || 'Student'; const role = state.organizerAuthenticated ? 'Organizer' : isDemoOrganizer() ? 'Organizer (public demo)' : 'Student'; return `<div class="shell"><aside class="sidebar"><div><div class="brand"><div class="logo">✦</div><div><strong>Campus<span>Connect</span></strong><small>Student Portal</small></div></div><nav class="nav"><button data-page="home" class="${state.page==='home'?'active':''}">${icon('⌂')} HOME</button><button data-page="events" class="${state.page==='events'?'active':''}">${icon('◫')} EVENTS</button><button data-page="registrations" class="${state.page==='registrations'?'active':''}">${icon('✓')} MY REGISTRATIONS</button></nav></div><div class="identity"><strong>Current role: ${escapeHtml(role)}</strong><label for="user-id">Student UUID for live registration</label><input id="user-id" value="${escapeHtml(userId())}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /><label for="student-name">Display name</label><input id="student-name" value="${escapeHtml(name)}" placeholder="Your name" /></div></aside><main class="main"><header class="topbar"><label class="search">⌕ <input id="search" value="${escapeHtml(state.query)}" placeholder="Search campus events, hackathons, workshops..." /></label><div class="profile"><div class="avatar">${escapeHtml(name.charAt(0).toUpperCase() || 'S')}</div><div><b>${escapeHtml(name)}</b><span>${escapeHtml(role)}</span></div></div></header><section class="content">${content}</section></main></div><div id="toast" class="toast hidden"></div>`; }
function eventCard(event, compact = false) { const demo = event.is_demo === true; const registered = state.registrations.some(reg => String(reg.event?.id || reg.event_id) === String(event.id)); const location = event.location || event.venue || 'Campus venue TBA'; const type = event.category || event.type || 'Campus event'; const capacity = event.capacity ? `${event.capacity} seats` : 'Open registration'; const registerButton = `<button class="register ${registered?'registered':''}" data-register="${event.id}" ${registered?'disabled':''}>${registered?'Registered':'Register'}</button>`; return `<article class="event-card"><div class="event-date"><span>${month(event)}</span><b>${day(event)}</b></div><div class="event-info"><div class="tag">${demo?'Demo · ':''}${escapeHtml(type)}</div><h3 class="event-title">${escapeHtml(event.title || 'Untitled event')}</h3><div class="details">📅 ${prettyDate(event)} &nbsp; · &nbsp; 📍 ${escapeHtml(location)}<br>${escapeHtml(capacity)}</div>${compact ? '' : `<div class="event-footer"><span class="muted">${escapeHtml(event.description || 'Discover, learn, and connect with your campus community.').slice(0,95)}</span>${registerButton}</div>`}</div>${compact ? `<div class="event-footer">${registerButton}</div>` : ''}</article>`; }
function home() { const events = filteredEvents().slice(0,4); return layout(`<section class="hero"><span class="eyebrow">● College events · Welcome back</span><h1>Hello ${escapeHtml(localStorage.getItem('campusconnect_name') || 'Student')},<br>Good morning!</h1><p>Find the next workshop, hackathon, or campus celebration—and reserve your spot in a few seconds.</p><button class="primary" data-page="events">Explore events →</button></section><div class="section-head"><div><h2>Upcoming events</h2><p>Live API events, with demo listings when none are available</p></div><button data-page="events">View all →</button></div><div class="grid">${state.loading ? '<div class="loading">Loading events…</div>' : events.length ? events.map(event => eventCard(event)).join('') : '<div class="empty">No matching events.</div>'}</div>`); }
function organizerTools() { return `<section class="organizer-tools"><div><strong>Public demo organizer</strong><p>Anyone can try adding events. New events and this role are saved only in the current browser, not in Supabase.</p></div><button class="role-toggle" data-toggle-demo-role>${isDemoOrganizer() ? 'Switch to Student' : 'Switch to Public Organizer Demo'}</button>${isDemoOrganizer() ? '<form id="event-form" class="event-form"><label>Event title<input name="title" maxlength="120" required /></label><label>Date<input name="event_date" type="date" required /></label><label>Location<input name="location" maxlength="120" required /></label><label>Category<input name="category" maxlength="60" value="Workshop" /></label><label>Capacity<input name="capacity" type="number" min="1" max="10000" value="50" required /></label><label class="form-wide">Description<textarea name="description" rows="3" maxlength="500"></textarea></label><button class="primary form-wide" type="submit">Add event</button></form>' : ''}</section>`; }
function liveOrganizerTools() { if (!state.authEnabled) return '<section class="organizer-tools"><strong>Live event publishing is not configured.</strong><p>Sign-in requires Supabase Auth and private server configuration. The public demo form above remains browser-only.</p></section>'; if (!state.organizerAuthenticated) return '<section class="organizer-tools"><strong>Organizer sign-in</strong><p>Sign in with the organizer username and the password set for its Supabase Auth account.</p><form id="organizer-login-form" class="event-form"><label>Username<input name="username" autocomplete="username" required /></label><label>Password<input name="password" type="password" autocomplete="current-password" required /></label><button class="primary form-wide" type="submit">Sign in</button></form></section>'; return `<section class="organizer-tools"><div><strong>Live organizer: ${escapeHtml(state.organizerUsername)}</strong><p>Events created here are published to the CampusConnect events feed.</p><button class="role-toggle" data-organizer-logout>Sign out</button></div><form id="live-event-form" class="event-form"><label>Event title<input name="title" maxlength="120" required /></label><label>Date<input name="event_date" type="date" required /></label><label>Location<input name="location" maxlength="120" required /></label><label>Category<input name="category" maxlength="60" value="Workshop" /></label><label>Capacity<input name="capacity" type="number" min="1" max="10000" value="50" required /></label><label class="form-wide">Description<textarea name="description" rows="3" maxlength="500"></textarea></label><button class="primary form-wide" type="submit">Publish event</button></form></section>`; }
function eventsPage() { const events = filteredEvents(); return layout(`<div class="page-title"><h1>Campus Events & Workshops</h1><p>Explore what is happening around campus and reserve your place.</p></div>${organizerTools()}${liveOrganizerTools()}<div class="filters"><button class="filter active">All events</button><button class="filter" data-sort="date">Upcoming date</button></div><div class="list">${state.loading ? '<div class="loading">Loading events…</div>' : events.length ? events.map(event => eventCard(event, true)).join('') : '<div class="empty">No matching events.</div>'}</div>`); }
function registrationsPage() { const items = state.registrations.map(reg => reg.event || state.events.find(event => event.id === reg.event_id)).filter(Boolean); return layout(`<div class="page-title"><h1>My Registered Events</h1><p>Live registrations and browser-only demo registrations appear here.</p></div>${!userId() ? '<div class="setup"><h3>Live events require a student UUID</h3><p>Enter your UUID in the sidebar to load live registrations. Demo registrations are saved only in this browser.</p></div>' : ''}${state.loading ? '<div class="loading">Loading registrations…</div>' : items.length ? `<div class="list">${items.map(event => eventCard(event, true)).join('')}</div>` : '<div class="empty">You have no event registrations yet. Browse Events to get started.</div>'}`); }
function filteredEvents() { const q = state.query.trim().toLowerCase(); return [...state.events].filter(event => !q || `${event.title || ''} ${event.description || ''} ${event.location || ''}`.toLowerCase().includes(q)).sort((a,b) => eventDate(a) - eventDate(b)); }
function render() { $('#app').innerHTML = state.page === 'home' ? home() : state.page === 'events' ? eventsPage() : registrationsPage(); bind(); }
function toast(message, error = false) { const target = $('#toast'); target.textContent = message; target.className = `toast ${error?'error':''}`; clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => target.className='toast hidden', 3600); }
async function load() {
  state.loading = true;
  render();
  try {
    const events = await api('/api/events');
    state.events = events.length ? events : demoEvents;
  } catch (error) {
    state.events = demoEvents;
    toast(`Could not reach the API at ${API_BASE}: ${error.message}. Showing demo events instead.`, true);
  }
  try {
    const localEvents = JSON.parse(localStorage.getItem(DEMO_EVENTS_KEY) || '[]');
    if (!Array.isArray(localEvents)) throw new Error('Saved demo events are invalid.');
    const localEventIds = new Set(localEvents.map(event => event.id));
    state.events = [...state.events.filter(event => !localEventIds.has(event.id)), ...localEvents];
  } catch (error) {
    toast(`Could not load locally saved demo events: ${error.message}`, true);
  }
  let liveRegistrations = [];
  if (userId()) {
    try {
      liveRegistrations = await api('/api/me/registrations');
    } catch (error) {
      liveRegistrations = [];
      toast(`Could not load registrations: ${error.message}`, true);
    }
  }
  try {
    const demoRegistrations = JSON.parse(localStorage.getItem(DEMO_REGISTRATIONS_KEY) || '[]');
    if (!Array.isArray(demoRegistrations)) throw new Error('Saved demo registrations are invalid.');
    state.registrations = [...liveRegistrations, ...demoRegistrations];
  } catch (error) {
    state.registrations = liveRegistrations;
    toast(`Could not load demo registrations: ${error.message}`, true);
  }
  try {
    const organizer = await api('/api/auth/me');
    state.authEnabled = organizer.enabled;
    state.organizerAuthenticated = organizer.authenticated;
    state.organizerUsername = organizer.username || '';
  } catch (error) {
    state.authEnabled = false;
    state.organizerAuthenticated = false;
    toast(`Could not check organizer sign-in: ${error.message}`, true);
  }
  state.loading = false;
  render();
}
function createLocalEvent(event) {
  event.preventDefault();
  if (!isDemoOrganizer()) {
    toast('Switch to the demo organizer role before adding an event.', true);
    return;
  }
  const formData = new FormData(event.currentTarget);
  const title = String(formData.get('title') || '').trim();
  const eventDateValue = String(formData.get('event_date') || '');
  const date = new Date(`${eventDateValue}T12:00:00`);
  const location = String(formData.get('location') || '').trim();
  const capacity = Number(formData.get('capacity'));
  if (!title || Number.isNaN(date.getTime()) || !location || !Number.isInteger(capacity) || capacity < 1) {
    toast('Enter an event title, valid date, location, and whole-number capacity.', true);
    return;
  }
  const createdEvent = {
    id: `local-${Date.now()}`,
    title,
    event_date: date.toISOString(),
    location,
    category: String(formData.get('category') || '').trim() || 'Campus event',
    capacity,
    description: String(formData.get('description') || '').trim(),
    is_demo: true,
  };
  try {
    const localEvents = JSON.parse(localStorage.getItem(DEMO_EVENTS_KEY) || '[]');
    if (!Array.isArray(localEvents)) throw new Error('Saved demo events are invalid.');
    localEvents.push(createdEvent);
    localStorage.setItem(DEMO_EVENTS_KEY, JSON.stringify(localEvents));
    state.events = [...state.events, createdEvent];
    render();
    toast('Demo event added in this browser.');
  } catch (error) {
    toast(`Could not save the demo event: ${error.message}`, true);
  }
}
function readEventForm(form) {
  const formData = new FormData(form);
  const title = String(formData.get('title') || '').trim();
  const eventDateValue = String(formData.get('event_date') || '');
  const date = new Date(`${eventDateValue}T12:00:00`);
  const location = String(formData.get('location') || '').trim();
  const capacity = Number(formData.get('capacity'));
  if (!title || Number.isNaN(date.getTime()) || !location || !Number.isInteger(capacity) || capacity < 1 || capacity > 10000) {
    throw new Error('Enter an event title, valid date, location, and capacity from 1 to 10000.');
  }
  return {
    title,
    event_date: date.toISOString(),
    location,
    category: String(formData.get('category') || '').trim() || 'Campus event',
    capacity,
    description: String(formData.get('description') || '').trim(),
  };
}
async function loginOrganizer(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const credentials = {
    username: String(formData.get('username') || '').trim(),
    password: String(formData.get('password') || ''),
  };
  form.reset();
  try {
    const result = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(credentials) });
    state.organizerAuthenticated = result.authenticated;
    state.organizerUsername = result.username;
    render();
    toast('Organizer signed in.');
  } catch (error) {
    toast(error.message, true);
  }
}
async function logoutOrganizer() {
  try {
    await api('/api/auth/logout', { method: 'POST', body: '{}' });
    state.organizerAuthenticated = false;
    state.organizerUsername = '';
    render();
    toast('Organizer signed out.');
  } catch (error) {
    toast(error.message, true);
  }
}
async function createLiveEvent(event) {
  event.preventDefault();
  try {
    const payload = readEventForm(event.currentTarget);
    const created = await api('/api/events', { method: 'POST', body: JSON.stringify(payload) });
    state.events = [...state.events, created];
    render();
    toast('Event published.');
  } catch (error) {
    toast(error.message, true);
  }
}
async function register(eventId) {
  const event = state.events.find(item => String(item.id) === String(eventId));
  if (event?.is_demo === true) {
    try {
      const demoRegistrations = JSON.parse(localStorage.getItem(DEMO_REGISTRATIONS_KEY) || '[]');
      if (!Array.isArray(demoRegistrations)) throw new Error('Saved demo registrations are invalid.');
      if (demoRegistrations.some(reg => String(reg.event_id) === String(event.id))) {
        toast('You are already registered for this demo event.', true);
        return;
      }
      const registration = { id: `demo-registration-${Date.now()}`, event_id: event.id, event };
      demoRegistrations.push(registration);
      localStorage.setItem(DEMO_REGISTRATIONS_KEY, JSON.stringify(demoRegistrations));
      state.registrations = [...state.registrations, registration];
      render();
      toast('Demo registration saved in this browser only; it is not a real reservation.');
    } catch (error) {
      toast(`Could not save demo registration: ${error.message}`, true);
    }
    return;
  }
  if (!isUuid(userId())) {
    toast('Enter a valid student UUID in the sidebar before registering for a live event.', true);
    return;
  }
  const button = $(`[data-register="${eventId}"]`);
  if (button) { button.disabled = true; button.textContent = 'Registering…'; }
  try {
    await api('/api/registrations',{method:'POST',body:JSON.stringify({event_id:eventId,user_id:userId()})});
    toast('You are registered—your pass is now in My Registrations.');
    state.registrations = [...await api('/api/me/registrations'), ...state.registrations.filter(reg => reg.event?.is_demo === true)];
    render();
  } catch (error) {
    toast(error.message, true);
    if (button) { button.disabled=false; button.textContent='Register'; }
  }
}
function bind() { document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => { state.page=button.dataset.page; render(); if (state.page === 'registrations' && userId()) load(); })); document.querySelectorAll('[data-register]').forEach(button => button.addEventListener('click', () => register(button.dataset.register))); const toggleDemoRole = $('[data-toggle-demo-role]'); if (toggleDemoRole) toggleDemoRole.addEventListener('click', () => { localStorage.setItem(DEMO_ROLE_KEY, isDemoOrganizer() ? 'student' : 'organizer'); render(); }); const eventForm = $('#event-form'); if (eventForm) eventForm.addEventListener('submit', createLocalEvent); const loginForm = $('#organizer-login-form'); if (loginForm) loginForm.addEventListener('submit', loginOrganizer); const logoutButton = $('[data-organizer-logout]'); if (logoutButton) logoutButton.addEventListener('click', logoutOrganizer); const liveEventForm = $('#live-event-form'); if (liveEventForm) liveEventForm.addEventListener('submit', createLiveEvent); const search = $('#search'); if (search) search.addEventListener('input', event => { state.query=event.target.value; const start=search.selectionStart; render(); const next=$('#search'); next.focus(); next.setSelectionRange(start,start); }); const id = $('#user-id'); if (id) id.addEventListener('change', event => { localStorage.setItem(STORAGE_KEY,event.target.value.trim()); load(); }); const name = $('#student-name'); if (name) name.addEventListener('change', event => { localStorage.setItem('campusconnect_name',event.target.value.trim() || 'Student'); render(); }); document.querySelector('[data-sort]')?.addEventListener('click', () => { state.events.sort((a,b)=>eventDate(a)-eventDate(b)); render(); }); }
load();
