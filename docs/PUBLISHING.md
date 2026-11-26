# Publication files and status

The release contains an English main article and a Chinese article:

- `articles/substack.en.md`
- `articles/substack.zh.md`

The articles' figures are in `figures/`, with both PNG and SVG. Their relative evidence links work within the repository or extracted project archive. A self-contained HTML reader can embed figures and referenced evidence without any script or remote asset:

```bash
python -m pip install -r requirements-publication.txt
python scripts/render_articles.py --output private/publication
```

After a public repository URL has been created and verified, `--repository-url VERIFIED_URL` can instead point evidence links to that repository's `main` branch. Do not describe a planned repository URL as published before its remote files have been verified.

## Substack preparation

Use the English article as the main post and the Chinese article as a separate edition or companion. The Markdown text, tables, original figure files and source links are ready for editorial transfer. Upload the actual PNGs as post images and preserve captions explaining that the charts are structural model outputs. Check the table and link rendering in the destination editor before publication.

No post has been created or sent from a Substack account by this release process. No claim is made that Substack accepts a particular Markdown/HTML import path or that rich-text image copying has been tested. The self-contained HTML is a reading/review deliverable; it is not proof of an external post.

## GitHub

Public repository publication is authorized. The final publication receipt must record the actual repository URL and commit after a successful write and readback. If repository creation or authentication is unavailable, retain the full publishable archive and state that the remote publication remains pending. Never substitute a different account or public service without authorization.

## Scope in headlines

Report the number of source records actually scored, the named model versions and the six-test result. Preserve the incomplete global coverage, traditional interpretation limits and deferred outcome validation. Avoid a title that implies a million-chart global study, a verified generational death forecast or completed external peer review.
