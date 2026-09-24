# PlateAI website

Static marketing site for PlateAI — Home / About / Blog / Support, plus Terms of Use, Privacy Policy, and 5 launch blog posts. No build step; plain HTML/CSS/JS.

## Structure

```
index.html          Main site (Home, About, Blog, Support — tab-switched, no reload)
terms.html           Terms of Use
privacy.html         Privacy Policy
blog/                Individual blog post pages, linked from the Blog tab
assets/              Images (app icon, hero photo, app screenshots)
```

## Local preview

Any static server works, e.g.:

```
python3 -m http.server 8000
```

then open `http://localhost:8000`.

## Deploying with GitHub Pages

1. Push this repo to GitHub.
2. In the repo settings, go to **Pages** → **Build and deployment** → **Source: Deploy from a branch**.
3. Pick the `main` branch and the `/ (root)` folder, save.
4. Your site will be live at `https://<username>.github.io/<repo-name>/` within a minute or two.
5. Optional: add a custom domain in the same Pages settings and point its DNS at GitHub Pages.

## Before going live

- Swap the placeholder App Store links (`href="#"` search — there shouldn't be any left, but double check) for your live listing once published: `https://apps.apple.com/pl/app/ai-calorie-counter-plateai/id6738055240` is already wired in throughout.
- `support@` / privacy contact emails are already set to the real addresses provided (`plateaibusiness0@gmail.com`, `yevhen.basistyi@gmail.com`).
- New blog posts: copy an existing file under `blog/`, edit the content, add a card linking to it from the Blog tab in `index.html`, then run `python3 tools/build_i18n.py` (see below).

## Translations

Only the English pages (`index.html`, `blog/*.html`) are edited by hand. The language folders (`es/`, `de/`, `fr/`, `pt/`, `pl/`, `uk/`, `ru/`, `cs/`) are **generated** — don't edit them.

```
tools/build_i18n.py    build script (needs: pip install beautifulsoup4)
i18n/source.json       every English text segment, keyed by id (generated)
i18n/<lang>.json       {id: translation} per language
```

`python3 tools/build_i18n.py` writes the language folders, the nav language picker, `hreflang`/canonical tags, and `sitemap.xml`. A language is only published when it has a translation for every segment.

After adding or editing English text:

1. Run `python3 tools/build_i18n.py` — it lists how many segments each language is missing.
2. `python3 tools/build_i18n.py --todo de` writes `i18n/todo.de.json` (id → English for missing segments).
3. Add those ids with translations to `i18n/de.json` (or `i18n/de.part2.json`; run `--merge` to fold chunks in). Keep HTML tags and `href`s identical — the build rejects mismatches.
4. Rebuild and commit the generated folders.

To add a language, add it to `LANGS` in the script and create `i18n/<code>.json`.
