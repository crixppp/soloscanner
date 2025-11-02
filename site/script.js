const packSelect = document.querySelector('[data-js="pack-select"]');
const pricePanel = document.querySelector('[data-js="price-panel"]');
const priceDetails = document.querySelector('[data-js="price-details"]');
const statusEl = document.querySelector('[data-js="status"]');
const productLink = document.querySelector('[data-js="product-link"]');
const retailerEl = document.querySelector('[data-js="retailer"]');
const suburbEl = document.querySelector('[data-js="suburb"]');
const priceTotalEl = document.querySelector('[data-js="price-total"]');
const priceUnitEl = document.querySelector('[data-js="price-unit"]');
const checkedAtEl = document.querySelector('[data-js="checked-at"]');
const updatedAtEl = document.querySelector('[data-js="updated-at"]');
const can = document.querySelector('[data-js="can"]');
const canInner = document.querySelector('[data-js="can-inner"]');
const page = document.querySelector('[data-js="page"]');

const AGE_STORAGE_KEY = 'soloScannerAgeVerified';
const AGE_STORAGE_TTL = 1000 * 60 * 60 * 24 * 30; // 30 days
const pricesEndpoint = '../data/prices.json';

let priceData = null;
let lastPackSize = null;

async function fetchPrices() {
  try {
    const response = await fetch(pricesEndpoint, {
      headers: {
        'Cache-Control': 'no-cache',
      },
    });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch prices', error);
    throw error;
  }
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
  }).format(value);
}

function formatTimestamp(timestamp) {
  if (!timestamp) return '—';
  const date = new Date(timestamp * 1000);
  return new Intl.DateTimeFormat('en-AU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function getBestPrice(packSize) {
  if (!priceData || !Array.isArray(priceData.items)) return null;
  const items = priceData.items.filter((item) => Number(item.pack_size) === Number(packSize));
  if (!items.length) return null;
  items.sort((a, b) => a.price_total - b.price_total);
  return items[0];
}

function updatePrice(packSize) {
  const result = getBestPrice(packSize);
  if (!result) {
    statusEl.textContent = 'No live pricing for this pack size yet.';
    priceDetails.hidden = true;
    productLink.hidden = true;
    updatedAtEl.textContent = priceData?.updated_at
      ? `Last scrape: ${formatTimestamp(priceData.updated_at)}`
      : '';
    return;
  }

  retailerEl.textContent = result.retailer;
  suburbEl.textContent = result.suburb;
  priceTotalEl.textContent = formatCurrency(result.price_total);
  priceUnitEl.textContent = formatCurrency(result.price_unit);
  checkedAtEl.textContent = formatTimestamp(result.checked_at);
  productLink.href = result.url;
  productLink.hidden = !result.url;
  priceDetails.hidden = false;
  statusEl.textContent = `Cheapest ${packSize}x pack found.`;
  updatedAtEl.textContent = priceData.updated_at
    ? `Last scrape: ${formatTimestamp(priceData.updated_at)}`
    : '';
}

function animateCan(packSize) {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  page.dataset.motion = reduceMotion ? 'reduce' : 'default';

  if (reduceMotion) {
    pricePanel.classList.remove('is-active');
    requestAnimationFrame(() => {
      pricePanel.classList.add('is-active');
    });
    updatePrice(packSize);
    lastPackSize = packSize;
    return;
  }

  if (lastPackSize === null) {
    canInner.style.transform = 'rotateY(180deg)';
    updatePrice(packSize);
    lastPackSize = packSize;
    return;
  }

  can.setAttribute('data-rotating', 'true');
  canInner.style.transform = canInner.style.transform === 'rotateY(0deg)' ? 'rotateY(180deg)' : 'rotateY(0deg)';

  setTimeout(() => {
    updatePrice(packSize);
    can.removeAttribute('data-rotating');
    lastPackSize = packSize;
  }, 450);
}

async function initialise() {
  try {
    priceData = await fetchPrices();
    const initialPack = packSelect.value;
    animateCan(initialPack);
  } catch (error) {
    statusEl.textContent = 'Unable to load pricing right now.';
  }
}

function enforceAgeGate() {
  const dialog = document.querySelector('[data-js="age-modal"]');
  if (!dialog) return;

  const stored = localStorage.getItem(AGE_STORAGE_KEY);
  const now = Date.now();

  if (stored) {
    try {
      const { acceptedAt } = JSON.parse(stored);
      if (acceptedAt && now - acceptedAt < AGE_STORAGE_TTL) {
        return;
      }
    } catch (error) {
      console.warn('Unable to read age gate storage', error);
    }
  }

  dialog.addEventListener('close', () => {
    if (dialog.returnValue === 'confirm') {
      localStorage.setItem(AGE_STORAGE_KEY, JSON.stringify({ acceptedAt: Date.now() }));
    } else {
      window.location.href = 'https://google.com';
    }
  });

  if (typeof dialog.showModal === 'function') {
    dialog.showModal();
  }
}

packSelect.addEventListener('change', (event) => {
  const packSize = event.target.value;
  animateCan(packSize);
});

enforceAgeGate();
initialise();
