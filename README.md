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
- New blog posts: copy an existing file under `blog/`, edit the content, then add a card linking to it from the Blog tab in `index.html`.
