# Solo Scanner

Solo Scanner is a dark, modern single-page site that highlights the cheapest price for Hard Rated (formerly Hard Solo) RTD packs across Melbourne, VIC. Pricing data is sourced from major liquor retailers using a scheduled GitHub Action and saved to `data/prices.json` for the frontend to read.

## Repository structure

```
├── site/                  # Static frontend deployed via GitHub Pages
│   ├── index.html         # 3D can UI with pack selector and age gate
│   ├── styles.css         # Dark theme and rotating can styling
│   └── script.js          # Fetches pricing and drives animation
├── data/prices.json       # Generated price cache updated by the scraper
├── scraper/
│   ├── scraper.py         # Fetches retailer APIs and writes prices.json
│   ├── config.example.json# Sample configuration with pack metadata
│   └── requirements.txt   # Python dependencies for the scraper
└── .github/workflows/
    └── scrape.yml         # Runs the scraper every three hours
```

## Frontend

The site is built with vanilla HTML/CSS/JS. It renders a rotating Hard Rated can that flips between the front selection label and the rear pricing panel when the user changes pack size. Users with reduced-motion preferences see a cross-fade instead of a spin. First-time visitors must complete an age verification modal; consent is remembered for 30 days in `localStorage`.


To view the site locally, open `site/index.html` in a browser or serve the directory with any static web server. When hosted on GitHub Pages, make sure the Pages source is set to the `/site` folder (Settings → Pages → Build and deployment).

## Scraper configuration

`scraper/scraper.py` loads product metadata from `scraper/config.json`. Copy the provided template and fill in retailer-specific details:

```bash
cp scraper/config.example.json scraper/config.json
```

Each pack entry should include:

- `retailer`: Display name in the UI
- `suburb`: Store location to surface alongside the retailer
- `pack_size`: Numeric can count (1, 4, 10, or 30)
- `source`: One of `dan_murphys`, `bws`, `liquorland`, `first_choice`, `coles`, or `woolworths`
- `product_id`: Identifier required by the corresponding retailer API
- `url`: Public product URL to expose in the UI
- `store_id`: Optional store identifier (used by Dan Murphy’s)
- `headers`/`extra`: Optional overrides for unusual request flows

The scraper currently knows how to talk to the following APIs:

| Retailer      | Notes |
| ------------- | ----- |
| Dan Murphy's  | Unofficial JSON detail endpoint via `api.danmurphys.com.au` |
| BWS           | Internal JSON endpoint read by the storefront |
| Liquorland    | GraphQL endpoint shared with First Choice |
| First Choice  | Uses the same GraphQL query as Liquorland |
| Coles         | Official `api.coles.com.au` endpoint (requires an API key) |
| Woolworths    | Public JSON product endpoint |

Place sensitive credentials in GitHub repository secrets (e.g. `COLES_API_KEY`). The workflow surfaces them to the scraper at runtime.

### Running manually

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scraper/requirements.txt
python scraper/scraper.py
```

The script writes the latest data to `data/prices.json` and logs any failures without aborting the entire run. Successful entries capture the total and unit price, retailer metadata, and Unix timestamps for freshness tracking.

## Automation

`.github/workflows/scrape.yml` executes the scraper every three hours and on manual dispatch. After running, it commits `data/prices.json` back to the repository only if changes are detected. Configure the workflow with the required secrets (e.g. `COLES_API_KEY`) under *Settings → Secrets and variables → Actions*.

## Development notes

- Keep `data/prices.json` versioned so the frontend always has a baseline payload.
- Update `scraper/config.json` whenever new pack sizes or retailers are introduced.
- The frontend expects numeric `pack_size` values matching the dropdown options.
- To customise the can art further, replace the CSS gradients or layer in an SVG background.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
